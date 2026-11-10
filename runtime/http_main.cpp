#ifdef _WIN32
#ifndef _WIN32_WINNT
#define _WIN32_WINNT 0x0A00
#endif
#endif
#define CPPHTTPLIB_OPENSSL_SUPPORT
#define CPPHTTPLIB_REQUEST_URI_MAX_LENGTH 2048
#include "third_party/httplib.h"
#include "nex_host.h"
#include "nex_io.h"
#include "nex_json.h"
#include "nex_auth.h"
#ifdef _WIN32
#include "nex_host_windows.h"
#endif
#ifdef NEX_HTTP_FILES_ENABLED
#include "nex_files.h"
#endif
#ifdef NEX_PRIVATE_TASK_PROFILE_HTTP
#include "nex_profile.h"
#endif
#ifdef NEX_ASYNC_TASKS
#include "nex_task_limits.h"
#endif
#ifdef NEX_FOREIGN_ENABLED
#include "nex_foreign.h"
#endif
#include <openssl/crypto.h>
#include <openssl/evp.h>
#include <array>
#include <csignal>
#include <filesystem>
#include <fstream>
#include <iostream>
#include <optional>
#include <regex>

#ifdef NEX_ASYNC_TASKS
extern "C" nexrt::Handle *nex_server_task_dispatch(nexrt::Handle *request,unsigned workers);
extern "C" const nexrt::TaskExecutionLimits *nex_server_task_limits();
#else
extern "C" nexrt::Handle *nex_server_dispatch(nexrt::Handle *request);
#endif
namespace {
namespace fs=std::filesystem;
std::atomic<bool> interrupted{false};
static_assert(std::atomic<bool>::is_always_lock_free);
void signal(int){interrupted=1;}
std::string read(const std::string &path){std::ifstream file(path,std::ios::binary);if(!file)throw std::runtime_error("cannot read configured file");return {std::istreambuf_iterator<char>(file),{}};}
std::array<unsigned char,32> digest(const std::string &token){
  std::array<unsigned char,32> out{};unsigned size=0;
  if(EVP_Digest(token.data(),token.size(),out.data(),&size,EVP_sha256(),nullptr)!=1||size!=out.size())throw std::runtime_error("token digest failed");return out;
}
struct Credential {std::string user;std::array<unsigned char,32> hash;};
std::vector<Credential> credentials(const std::string &path){
  auto result=nexrt::decodeJSON(read(path),nexrt::authenticationSchema);if(!nexrt::isSuccess(result))throw std::runtime_error("invalid authentication file");
  auto data=nexrt::unwrap(result).object;
  if(data->values[0].object->text!="nex.auth/1")throw std::runtime_error("unsupported authentication file version");
  std::vector<Credential> out;std::set<std::array<unsigned char,32>> seen;
  for(const auto &item:data->values[1].object->values){
    auto user=item.object->values[0].object->text,text=item.object->values[1].object->text;
    if(user.empty()||user.size()>256||user.find('\0')!=std::string::npos||text.size()!=64)throw std::runtime_error("invalid authentication entry");
    Credential entry;entry.user=std::move(user);
    auto hex=[](char c)->unsigned {if(c>='0'&&c<='9')return c-'0';if(c>='a'&&c<='f')return c-'a'+10;throw std::runtime_error("token hashes must be lowercase SHA256 hex");};
    for(size_t i=0;i<32;++i)entry.hash[i]=static_cast<unsigned char>((hex(text[i*2])<<4)|hex(text[i*2+1]));
    if(!seen.insert(entry.hash).second)throw std::runtime_error("duplicate authentication token hash");out.push_back(std::move(entry));
  }
  if(out.empty()||out.size()>1024)throw std::runtime_error("authentication requires 1..1024 token entries");return out;
}
std::optional<std::string> authenticate(const httplib::Request &request,const std::vector<Credential> &entries){
  if(request.get_header_value_count("Authorization")!=1)return {};
  auto text=request.get_header_value("Authorization");if(text.size()<8||text.size()>256)return {};
  auto scheme=text.substr(0,7);std::transform(scheme.begin(),scheme.end(),scheme.begin(),[](unsigned char c){return char(std::tolower(c));});
  if(scheme!="bearer ")return {};auto hash=digest(text.substr(7));std::optional<std::string> user;
  for(const auto &entry:entries)if(CRYPTO_memcmp(hash.data(),entry.hash.data(),hash.size())==0)user=entry.user;
  return user;
}
void error(httplib::Response &response,int status,const std::string &code,const std::string &id=""){
  response.status=status;response.set_content("{\"error\":{\"code\":"+nexrt::quoted(code)+",\"message\":\"request failed\"},\"request_id\":"+nexrt::quoted(id)+"}","application/json; charset=utf-8");response.set_header("Cache-Control","no-store");
}
bool inside(const fs::path &path,const fs::path &root){auto relative=path.lexically_relative(root);for(const auto &part:relative)if(part=="..")return false;return !relative.is_absolute();}
bool corsOrigin(const std::string &value){
  if(value=="capacitor://localhost")return true;
  if(value.size()>300)return false;
  static const std::regex pattern(R"((https?)://([a-z0-9.-]+)(:([1-9][0-9]{0,4}))?)");
  std::smatch match;if(!std::regex_match(value,match,pattern))return false;
  auto host=match[2].str();if(host.size()>253)return false;
  size_t begin=0;do {auto end=host.find('.',begin);if(end==std::string::npos)end=host.size();auto label=host.substr(begin,end-begin);
    if(label.empty()||label.size()>63||label.front()=='-'||label.back()=='-')return false;
    begin=end+1;
  }while(begin<=host.size());
  if(match[4].matched){auto port=std::stoi(match[4].str());if(port>65535||(match[1]=="https"&&port==443)||(match[1]=="http"&&port==80))return false;}
  return true;
}
bool corsMethod(const std::string &method){return method=="GET"||method=="HEAD"||method=="POST"||method=="PUT"||method=="PATCH"||method=="DELETE"||method=="OPTIONS";}
bool corsHeaders(const httplib::Request &request){
  auto count=request.get_header_value_count("Access-Control-Request-Headers");if(count==0)return true;if(count!=1)return false;
  auto value=request.get_header_value("Access-Control-Request-Headers");if(value.empty()||value.size()>128)return false;
  size_t begin=0;std::set<std::string> seen;
  do {auto end=value.find(',',begin);if(end==std::string::npos)end=value.size();auto name=value.substr(begin,end-begin);
    auto first=name.find_first_not_of(" \t"),last=name.find_last_not_of(" \t");if(first==std::string::npos)return false;name=name.substr(first,last-first+1);
    std::transform(name.begin(),name.end(),name.begin(),[](unsigned char c){return char(std::tolower(c));});
    if((name!="authorization"&&name!="content-type")||!seen.insert(name).second)return false;
    begin=end+1;
  }while(begin<=value.size());return true;
}
struct Config {
  std::string host="127.0.0.1",auth,database,assets,cert,key,foreign,filesRoot;
  bool filesWritable=false,filesWriteSpecified=false;
  std::set<std::string> cors;
  int port=8080,workers=8,queue=64;uint64_t budget=1000000,timeout=5000;
#ifdef NEX_ASYNC_TASKS
  nexrt::TaskExecutionLimits taskLimits;
#endif
};
Config config(int argc,char **argv){
  Config c;
#ifdef NEX_ASYNC_TASKS
  auto ceilings=nex_server_task_limits();
  if(!ceilings)throw std::runtime_error("compiled HTTP task limits are absent");
  c.taskLimits=nexrt::parseTaskExecutionArguments(*ceilings,argc,argv);
#endif
  for(int i=1;i<argc;++i){
    std::string option=argv[i];if(i+1==argc)throw std::runtime_error("server option requires a value");std::string value=argv[++i];
#ifdef NEX_ASYNC_TASKS
    // The shared parser above validates the reserved namespace, duplicate
    // arguments and immutable ceilings before the server opens any resources.
    if(option.starts_with("--nex-task-"))continue;
#endif
    if(option=="--files-root"){
      if(!c.filesRoot.empty()||value.empty()||!fs::path(value).is_absolute())throw std::runtime_error("--files-root requires one absolute directory");
      c.filesRoot=value;
    }else if(option=="--files-write"){
      if(c.filesWriteSpecified||(value!="0"&&value!="1"))throw std::runtime_error("--files-write requires one0 or1 value");
      c.filesWriteSpecified=true;c.filesWritable=value=="1";
    }else if(option=="--host")c.host=value;else if(option=="--auth")c.auth=value;else if(option=="--database")c.database=value;else if(option=="--static")c.assets=value;else if(option=="--cert")c.cert=value;else if(option=="--key")c.key=value;else if(option=="--foreign")c.foreign=value;
    else if(option=="--cors-origin"){if(!corsOrigin(value)||!c.cors.insert(value).second||c.cors.size()>16)throw std::runtime_error("CORS requires1..16 distinct exact origins; wildcard, null, credentials and paths are unsupported");}
    else{
      uint64_t number=0;auto parsed=std::from_chars(value.data(),value.data()+value.size(),number);if(parsed.ec!=std::errc()||parsed.ptr!=value.data()+value.size())throw std::runtime_error("invalid numeric server option");
      if(option=="--port"&&number<=65535)c.port=int(number);
      else if(option=="--workers"&&number>=1&&number<=64)c.workers=int(number);
      else if(option=="--queue"&&number>=1&&number<=1024)c.queue=int(number);
      else if(option=="--budget"&&number>=1&&number<=100000000)c.budget=number;
      else if(option=="--timeout-ms"&&number>=1&&number<=60000)c.timeout=number;
      else throw std::runtime_error("unknown or out-of-range server option");
    }
  }
#ifdef NEX_ASYNC_TASKS
  c.budget=std::min(c.budget,c.taskLimits.steps);
  c.timeout=std::min(c.timeout,c.taskLimits.timeoutMs);
#endif
  if(c.filesWriteSpecified&&c.filesRoot.empty())throw std::runtime_error("--files-write requires --files-root");
#ifndef NEX_HTTP_FILES_ENABLED
  if(!c.filesRoot.empty())throw std::runtime_error("server image has no filesystem adapter");
#endif
  if(c.auth.empty()||c.database.empty())throw std::runtime_error("server requires --auth FILE and --database FILE");
  if(c.cert.empty()!=c.key.empty())throw std::runtime_error("TLS requires both --cert FILE and --key FILE");
  if(!c.assets.empty()){
    auto root=fs::weakly_canonical(c.assets);if(!fs::is_regular_file(root/"index.html"))throw std::runtime_error("static root must contain built index.html");
    for(const auto &privateFile:{c.auth,c.database,c.cert,c.key})if(!privateFile.empty()&&inside(fs::weakly_canonical(privateFile),root))throw std::runtime_error("server credentials and database must be outside the static root");
    c.assets=root.string();
  }
  return c;
}
std::string mime(const fs::path &path){
  static const std::map<std::string,std::string> types={{".html","text/html; charset=utf-8"},{".css","text/css; charset=utf-8"},{".js","text/javascript; charset=utf-8"},{".json","application/json"},{".map","application/json"},{".txt","text/plain; charset=utf-8"},{".svg","image/svg+xml"},{".png","image/png"},{".jpg","image/jpeg"},{".webp","image/webp"},{".woff2","font/woff2"}};
  auto found=types.find(path.extension().string());return found==types.end()?"application/octet-stream":found->second;
}
}
int main(int argc,char **argv){
  try{
    auto c=config(argc,argv);
#ifdef NEX_HTTP_FILES_ENABLED
    // The operator chooses this capability explicitly. Pin its physical root
    // before workers start; each request receives a separate lexical child.
    std::unique_ptr<nexrt::TextFiles> configuredFiles;
    if(!c.filesRoot.empty())configuredFiles=std::make_unique<nexrt::TextFiles>(c.filesRoot,c.filesWritable);
#endif
#ifdef NEX_PRIVATE_TASK_PROFILE_HTTP
    // The collector is prepared by the private host before workers start.
    // These are common per-request limits, not a process-wide execution budget.
    nexrt::taskProfileLimits(c.taskLimits,{c.budget,c.timeout,c.taskLimits.workers});
#endif
#ifdef NEX_FOREIGN_ENABLED
    if(c.foreign.empty())c.foreign=nexrt::packagedForeignCatalogue();
    auto foreign=c.foreign.empty()?std::shared_ptr<nexrt::ForeignLibraries>{}:nexrt::loadForeignLibraries(c.foreign);
    if(foreign&&!c.assets.empty()){auto root=fs::weakly_canonical(c.assets);if(inside(fs::weakly_canonical(c.foreign),root))throw std::runtime_error("foreign catalogue must be outside the static root");for(const auto &directory:foreign->grantedDirectories())if(inside(fs::weakly_canonical(directory),root))throw std::runtime_error("foreign module directories must be outside the static root");}
#else
    if(!c.foreign.empty())throw std::runtime_error("server has no external calls");
#endif
    auto auth=credentials(c.auth);nexrt::Database::initialize(c.database);
    std::unique_ptr<httplib::Server> server;
    if(c.cert.empty())server=std::make_unique<httplib::Server>();else server=std::make_unique<httplib::SSLServer>(c.cert.c_str(),c.key.c_str());
    if(!server->is_valid())throw std::runtime_error("HTTP/TLS server configuration is invalid");
    server->new_task_queue=[&]{return new httplib::ThreadPool(c.workers,c.workers,c.queue);};
    server->set_payload_max_length(1024*1024);server->set_read_timeout(5);server->set_write_timeout(5);server->set_keep_alive_timeout(2);server->set_keep_alive_max_count(100);
    server->set_default_headers({{"X-Content-Type-Options","nosniff"}});
    server->Get("/health",[](const auto &,auto &response){response.set_content("{\"ok\":true}","application/json");response.set_header("Cache-Control","no-store");});
    server->set_pre_request_handler([&](const auto &request,auto &response){
      if(request.path.starts_with("/api/")&&!c.cors.empty()){
        // Decide before authentication/body buffering. Preflight never enters NEX
        // or a data transaction. A denied Origin cannot perform a mutation.
        response.set_header("Cache-Control","no-store");
        auto count=request.get_header_value_count("Origin");auto origin=request.get_header_value("Origin");
        bool preflight=request.has_header("Access-Control-Request-Method")||request.has_header("Access-Control-Request-Headers");
        response.set_header("Vary",preflight?"Origin, Access-Control-Request-Method, Access-Control-Request-Headers":"Origin");
        auto denied=[&](int status,const char *code){error(response,status,code);response.set_header("Connection","close");return httplib::Server::HandlerResponse::Handled;};
        if(count>1||(count==1&&(origin.empty()||!corsOrigin(origin))))return denied(403,"CORS_ORIGIN");
        bool allowed=count==1&&c.cors.contains(origin);
        bool same=count==1&&request.get_header_value_count("Host")==1&&origin==std::string(c.cert.empty()?"http://":"https://")+request.get_header_value("Host");
        if(count==1&&!allowed&&!same)return denied(403,"CORS_ORIGIN");
        if(allowed){response.set_header("Access-Control-Allow-Origin",origin);response.set_header("Access-Control-Expose-Headers","X-Request-Id");}
        if(preflight){
          if(request.method!="OPTIONS"||!allowed||request.get_header_value_count("Access-Control-Request-Method")!=1||
             !corsMethod(request.get_header_value("Access-Control-Request-Method"))||!corsHeaders(request)||
             request.has_header("Transfer-Encoding")||request.get_header_value_count("Content-Length")>1||
             (request.has_header("Content-Length")&&request.get_header_value("Content-Length")!="0"))return denied(400,"CORS_PREFLIGHT");
          response.status=204;response.set_header("Access-Control-Allow-Methods","GET, HEAD, POST, PUT, PATCH, DELETE, OPTIONS");
          response.set_header("Access-Control-Allow-Headers","Authorization, Content-Type");response.set_header("Connection","close");
          return httplib::Server::HandlerResponse::Handled;
        }
      }
      if(request.path.starts_with("/api/")&&!authenticate(request,auth)){error(response,401,"UNAUTHORIZED");response.set_header("WWW-Authenticate","Bearer");response.set_header("Connection","close");return httplib::Server::HandlerResponse::Handled;}
      if(request.path.starts_with("/api/")&&request.has_header("Content-Length")){
        auto text=request.get_header_value("Content-Length");uint64_t size=0;auto parsed=std::from_chars(text.data(),text.data()+text.size(),size);
        if(parsed.ec!=std::errc()||parsed.ptr!=text.data()+text.size()||size>1024*1024){error(response,size>1024*1024?413:400,"INVALID_BODY_LENGTH");response.set_header("Connection","close");return httplib::Server::HandlerResponse::Handled;}
      }
      return httplib::Server::HandlerResponse::Unhandled;
    });
    std::atomic<uint64_t> sequence{0};
    auto dispatch=[&](const httplib::Request &request,httplib::Response &response){
      auto id=std::to_string(++sequence);response.set_header("X-Request-Id",id);response.set_header("Cache-Control","no-store");
      auto user=authenticate(request,auth);if(!user){error(response,401,"UNAUTHORIZED",id);return;}
      try{
        nexrt::RequestScope scope(c.budget,c.timeout);scope.setCancellation([&]{return interrupted||request.is_connection_closed();});scope.poll();
#ifdef NEX_HTTP_FILES_ENABLED
        std::unique_ptr<nexrt::FileScope> filesScope;
        if(configuredFiles)filesScope=std::make_unique<nexrt::FileScope>(*configuredFiles);
#endif
#ifdef NEX_FOREIGN_ENABLED
        std::unique_ptr<nexrt::ForeignScope> foreignScope;if(foreign)foreignScope=std::make_unique<nexrt::ForeignScope>(foreign);
#endif
        bool writable=request.method!="GET"&&request.method!="HEAD"&&request.method!="OPTIONS";
        nexrt::Database db(c.database,*user,writable,nexrt::Database::TransactionStart::OnFirstOperation);nexrt::StorageScope capability(db);
        auto input=std::make_shared<nexrt::Data>(nexrt::Data::Record);input->text="std::http::Request";
        input->names={"method","path","query","body","user","request_id"};
        auto query=request.target.find('?');
        for(const auto &text:{request.method,request.path,query==std::string::npos?std::string():request.target.substr(query+1),request.body,*user,id})input->values.emplace_back(nexrt::string(text));
        auto argument=nexrt::makeHandle(nexrt::Value(input));
#ifdef NEX_ASYNC_TASKS
        auto returned=nex_server_task_dispatch(argument,c.taskLimits.workers);
#else
        auto returned=nex_server_dispatch(argument);
#endif
        auto result=nexrt::readHandle(returned).object;
        if(result->kind!=nexrt::Data::Record||result->text!="std::http::Response"||result->values.size()!=3)throw nexrt::Trap("E_RESPONSE","invalid response ABI",0);
        auto status=result->values[0].scalar;auto body=result->values[1].object->text,contentType=result->values[2].object->text;
        if(status<200||status>599||body.size()>1024*1024||contentType.empty()||contentType.size()>256||!std::all_of(contentType.begin(),contentType.end(),[](unsigned char c){return c>=32&&c<127;}))throw nexrt::Trap("E_RESPONSE","invalid response value",0);
        nex_release(returned);nex_release(argument);scope.poll();
        if(status<300){auto committed=db.commit();if(!nexrt::isSuccess(committed)){error(response,503,committed.object->text,id);return;}}
        else db.rollback();
        response.status=int(status);response.set_content(std::move(body),contentType);
      }
      catch(const nexrt::NativeSourceException &failure){error(response,500,"E_SOURCE_EXCEPTION",id);nexrt::printNativeSourceException(failure,id.c_str());}
      catch(const nexrt::Trap &trap){error(response,trap.code=="E_TIMEOUT"?504:trap.code=="E_CANCELLED"?499:trap.code=="E_LIMIT"?429:500,trap.code,id);std::fprintf(stderr,"request %s: %s at NEX line %lld\n",id.c_str(),trap.code.c_str(),static_cast<long long>(trap.line));if(auto located=dynamic_cast<const nexrt::LocatedTrap*>(&trap))nexrt::printNativeTrapText(trap.code,nexrt::trapMessage(trap),trap.line,located->source,id.c_str());}
      catch(const nexrt::DataError &failure){error(response,failure.code=="E_UTF8"?400:503,failure.code,id);}
      catch(const std::exception &){error(response,500,"E_RUNTIME",id);}
    };
    server->Get("/api/.*",dispatch);server->Post("/api/.*",dispatch);server->Put("/api/.*",dispatch);
    server->Patch("/api/.*",dispatch);server->Delete("/api/.*",dispatch);server->Options("/api/.*",dispatch);
    if(!c.assets.empty())server->Get("/.*",[&](const auto &request,auto &response){
      try{
        if(request.path.find('\0')!=std::string::npos){error(response,400,"INVALID_PATH");return;}
        fs::path relative=request.path.substr(1);for(const auto &part:relative)if(part==".."||part.string().starts_with('.')){error(response,404,"NOT_FOUND");return;}
        auto root=fs::path(c.assets),path=fs::weakly_canonical(root/relative);
        if(!inside(path,root)){error(response,404,"NOT_FOUND");return;}
        if(fs::is_directory(path))path/= "index.html";
        if(!fs::is_regular_file(path)&&relative.extension().empty())path=root/"index.html";
        if(!fs::is_regular_file(path)){error(response,404,"NOT_FOUND");return;}
        response.set_file_content(path.string(),mime(path));
      }catch(const std::exception &){error(response,404,"NOT_FOUND");}
    });
    server->set_error_handler([](const auto &,auto &response){if(response.body.empty())error(response,response.status,"HTTP_ERROR");});
    if(!server->is_valid())throw std::runtime_error("invalid HTTP route registration");
    int port=c.port;
    if(port){if(!server->bind_to_port(c.host,port))throw std::runtime_error("cannot bind HTTP server");}
    else {port=server->bind_to_any_port(c.host);if(port<1)throw std::runtime_error("cannot bind HTTP server");}
    std::signal(SIGINT,signal);std::signal(SIGTERM,signal);
#ifdef _WIN32
    // TerminateProcess cannot deliver a cooperative signal. A same-user host
    // can request cancellation through this protected per-process event.
    nexrt::host_windows::PrivateSecurity controlSecurity(EVENT_MODIFY_STATE|SYNCHRONIZE);
    SECURITY_ATTRIBUTES controlAttributes{sizeof(controlAttributes),&controlSecurity.descriptor,FALSE};
    auto controlName=L"Local\\NEX.Server.Stop."+std::to_wstring(GetCurrentProcessId());
    nexrt::host_windows::Handle control(CreateEventW(&controlAttributes,TRUE,FALSE,controlName.c_str()));
    if(!control.value||GetLastError()==ERROR_ALREADY_EXISTS)throw std::runtime_error("cannot create private server control event");
#endif
    std::atomic<bool> controlFailed{false};
    std::jthread shutdown([&](std::stop_token stop){
      while(!stop.stop_requested()&&!interrupted){
#ifdef _WIN32
        auto status=WaitForSingleObject(control.value,20);
        if(status==WAIT_OBJECT_0)interrupted=true;
        else if(status!=WAIT_TIMEOUT){controlFailed=true;interrupted=true;}
#else
        std::this_thread::sleep_for(std::chrono::milliseconds(20));
#endif
      }if(interrupted)server->stop();});
    std::cout<<"NEX server "<<(c.cert.empty()?"http":"https")<<"://"<<c.host<<":"<<port<<std::endl;
    bool listened=server->listen_after_bind();shutdown.request_stop();shutdown.join();server.reset();nex_runtime_finish();return !controlFailed&&(listened||interrupted)?0:1;
  }catch(const std::exception &e){std::cerr<<"NEX server: "<<e.what()<<'\n';return 1;}
}
