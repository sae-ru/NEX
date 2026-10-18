#define CPPHTTPLIB_OPENSSL_SUPPORT
#define CPPHTTPLIB_REQUEST_URI_MAX_LENGTH 2048
#include "third_party/httplib.h"
#include "nex_host.h"
#include "nex_io.h"
#include "nex_json.h"
#include "nex_auth.h"
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

extern "C" nexrt::Handle *nex_server_dispatch(nexrt::Handle *request);
namespace {
namespace fs=std::filesystem;
volatile std::sig_atomic_t interrupted=0;
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
struct Config {
  std::string host="127.0.0.1",auth,database,assets,cert,key,foreign;
  int port=8080,workers=8,queue=64;uint64_t budget=1000000,timeout=5000;
};
Config config(int argc,char **argv){
  Config c;
  for(int i=1;i<argc;++i){
    std::string option=argv[i];if(i+1==argc)throw std::runtime_error("server option requires a value");std::string value=argv[++i];
    if(option=="--host")c.host=value;else if(option=="--auth")c.auth=value;else if(option=="--database")c.database=value;else if(option=="--static")c.assets=value;else if(option=="--cert")c.cert=value;else if(option=="--key")c.key=value;else if(option=="--foreign")c.foreign=value;
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
#ifdef NEX_FOREIGN_ENABLED
        std::unique_ptr<nexrt::ForeignScope> foreignScope;if(foreign)foreignScope=std::make_unique<nexrt::ForeignScope>(foreign);
#endif
        bool writable=request.method!="GET"&&request.method!="HEAD"&&request.method!="OPTIONS";
        nexrt::Database db(c.database,*user,writable);nexrt::StorageScope capability(db);
        auto input=std::make_shared<nexrt::Data>(nexrt::Data::Record);input->text="std::http::Request";
        input->names={"method","path","query","body","user","request_id"};
        auto query=request.target.find('?');
        for(const auto &text:{request.method,request.path,query==std::string::npos?std::string():request.target.substr(query+1),request.body,*user,id})input->values.emplace_back(nexrt::string(text));
        auto argument=nexrt::makeHandle(nexrt::Value(input));auto returned=nex_server_dispatch(argument);auto result=nexrt::readHandle(returned).object;
        if(result->kind!=nexrt::Data::Record||result->text!="std::http::Response"||result->values.size()!=3)throw nexrt::Trap("E_RESPONSE","invalid response ABI",0);
        auto status=result->values[0].scalar;auto body=result->values[1].object->text,contentType=result->values[2].object->text;
        if(status<200||status>599||body.size()>1024*1024||contentType.empty()||contentType.size()>256||!std::all_of(contentType.begin(),contentType.end(),[](unsigned char c){return c>=32&&c<127;}))throw nexrt::Trap("E_RESPONSE","invalid response value",0);
        nex_release(returned);nex_release(argument);scope.poll();
        if(status<300){auto committed=db.commit();if(!nexrt::isSuccess(committed)){error(response,503,committed.object->text,id);return;}}
        else db.rollback();
        response.status=int(status);response.set_content(std::move(body),contentType);
      }catch(const nexrt::Trap &trap){error(response,trap.code=="E_TIMEOUT"?504:trap.code=="E_CANCELLED"?499:trap.code=="E_LIMIT"?429:500,trap.code,id);std::fprintf(stderr,"request %s: %s at NEX line %lld\n",id.c_str(),trap.code.c_str(),static_cast<long long>(trap.line));if(auto located=dynamic_cast<const nexrt::LocatedTrap*>(&trap))nexrt::printNativeTrap(trap.code.c_str(),trap.what(),trap.line,located->source,id.c_str());}
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
    std::jthread shutdown([&](std::stop_token stop){while(!stop.stop_requested()&&!interrupted)std::this_thread::sleep_for(std::chrono::milliseconds(20));if(interrupted)server->stop();});
    std::cout<<"NEX server "<<(c.cert.empty()?"http":"https")<<"://"<<c.host<<":"<<port<<std::endl;
    bool listened=server->listen_after_bind();shutdown.request_stop();shutdown.join();server.reset();nex_runtime_finish();return listened?0:1;
  }catch(const std::exception &e){std::cerr<<"NEX server: "<<e.what()<<'\n';return 1;}
}
