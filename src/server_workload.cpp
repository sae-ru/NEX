#include "nex/server_workload.h"
#include "nex/backend.h"
#include "nex_json.h"
#include "nex_value.h"
#include "llvm/ADT/StringExtras.h"
#include "llvm/Support/Error.h"
#include "llvm/Support/Program.h"
#include "llvm/Support/SHA256.h"
#include <algorithm>
#include <array>
#include <charconv>
#include <cerrno>
#include <cstdlib>
#include <filesystem>
#include <fcntl.h>
#include <sys/stat.h>
#include <unistd.h>
#ifdef _WIN32
#include "nex_host_windows.h"
#endif

namespace nex { namespace {
namespace fs=std::filesystem;
using Object=llvm::json::Object;using Value=llvm::json::Value;
[[noreturn]] void fail(const std::string &message,const char *code="E_SERVER_WORKLOAD"){throw Error(code,message);}
std::string sha(const std::string &text){return llvm::toHex(llvm::SHA256::hash(llvm::arrayRefFromStringRef(text)),true);}
std::string bounded(const std::string &path,size_t limit=1048576){
#ifdef _WIN32
  std::string text;
  try{text=nexrt::host_windows::readRegular(nexrt::platform::wide(path),limit);}
  catch(const nexrt::DataError &error){fail(error.what());}
#else
  struct File{int fd;~File(){if(fd>=0)::close(fd);}} file{::open(path.c_str(),O_RDONLY|O_NONBLOCK|O_NOFOLLOW|O_CLOEXEC)};
  struct stat info{};
  if(file.fd<0||::fstat(file.fd,&info)||!S_ISREG(info.st_mode)||info.st_size<0||uint64_t(info.st_size)>limit)fail("workload inputs require bounded regular non-symlink files");
  std::string text;std::array<char,65536> bytes{};
  for(;;){auto count=::read(file.fd,bytes.data(),bytes.size());if(count<0){if(errno==EINTR)continue;fail("cannot read workload input");}if(!count)break;if(size_t(count)>limit-text.size())fail("workload input exceeds its byte limit");text.append(bytes.data(),size_t(count));}
#endif
  try{nexrt::unicodeOffsets(text,false);}catch(const nexrt::DataError&){fail("workload input must be strict UTF-8");}return text;
}
void keys(const Object &object,const std::set<std::string> &allowed){for(const auto &[key,value]:object){(void)value;if(!allowed.contains(key.str()))fail("unknown workload field: "+key.str());}}
const Object &object(const Value *value){auto result=value?value->getAsObject():nullptr;if(!result)fail("workload field requires an object");return *result;}
std::string text(const Value *value,size_t maximum,bool empty=true){auto s=value?value->getAsString():std::nullopt;if(!s||s->size()>maximum||(!empty&&s->empty()))fail("workload text is missing or exceeds its bound");return s->str();}
std::string optionalText(const Object &o,const char *name,const std::string &fallback,size_t maximum){auto value=o.get(name);return value?text(value,maximum):fallback;}
int64_t integer(const Value *value,int64_t minimum,int64_t maximum){auto n=value?value->getAsInteger():std::nullopt;if(!n||*n<minimum||*n>maximum)fail("workload integer is missing or outside its bound");return *n;}
int64_t optionalInteger(const Object &o,const char *name,int64_t fallback,int64_t minimum,int64_t maximum){return o.get(name)?integer(o.get(name),minimum,maximum):fallback;}
bool digest(const std::string &value){return value.size()==64&&std::all_of(value.begin(),value.end(),[](char c){return(c>='0'&&c<='9')||(c>='a'&&c<='f');});}
bool variable(const std::string &s){auto alpha=[](char c){return(c>='A'&&c<='Z')||(c>='a'&&c<='z')||c=='_';};return !s.empty()&&s.size()<=128&&alpha(s[0])&&std::all_of(s.begin(),s.end(),[&](char c){return alpha(c)||(c>='0'&&c<='9');});}
void lexicalLimits(const std::string &source){
  bool quoted=false,escape=false;unsigned depth=0;
  for(size_t i=0;i<source.size();++i){char c=source[i];if(quoted){if(escape)escape=false;else if(c=='\\')escape=true;else if(c=='"')quoted=false;continue;}
    if(c=='"'){quoted=true;continue;}if(c=='{'||c=='['){if(++depth>33)fail("workload exceeds depth32");}else if(c=='}'||c==']'){if(depth)--depth;}
    else if(c=='-'||(c>='0'&&c<='9')){size_t end=i+1;while(end<source.size()&&std::string("0123456789.eE+-").find(source[end])!=std::string::npos)++end;
      auto token=source.substr(i,end-i);int64_t n=0;auto parsed=std::from_chars(token.data(),token.data()+token.size(),n);
      if(token.size()>20||parsed.ec!=std::errc()||parsed.ptr!=token.data()+token.size())fail("workload numbers require bounded finite integers");i=end-1;}
  }
}
}

ServerWorkload inspectServerWorkload(const std::string &root,const std::string &selection){
  ServerWorkload result;result.selection=fs::absolute(fs::path(selection).is_absolute()?fs::path(selection):fs::path(root)/selection).lexically_normal().string();
  std::error_code error;auto path=fs::canonical(result.selection,error);auto relative=path.lexically_relative(fs::canonical(root));
  if(error||relative.empty()||relative.is_absolute()||std::any_of(relative.begin(),relative.end(),[](const auto &p){return p==".."||p==".nex"||p==".git";}))fail("workload must be a regular project-confined file");
  result.path=path.string();result.source=bounded(result.selection);result.sha256=sha(result.source);
  try{nexrt::validateJSONText(result.source);}catch(const nexrt::DataError&){fail("workload requires bounded strict UTF-8 JSON with unique keys");}
  lexicalLimits(result.source);auto parsed=llvm::json::parse(result.source);if(!parsed){llvm::consumeError(parsed.takeError());fail("invalid workload JSON");}
  const auto &top=object(&*parsed);keys(top,{"schema","requests","phases","warmup","authorization_env","request_timeout_ms","startup_timeout_ms"});
  if(text(top.get("schema"),64)!="nex.server-workload/1")fail("expected nex.server-workload/1");
  auto requests=top.getArray("requests"),phases=top.getArray("phases");if(!requests||requests->empty()||requests->size()>128||!phases||phases->empty()||phases->size()>16)fail("workload requires1..128 requests and1..16 phases");
  for(const auto &value:*requests){const auto &row=object(&value);keys(row,{"method","path","body","content_type","expect"});
    auto method=optionalText(row,"method","GET",16);if(!std::set<std::string>{"GET","HEAD","POST","PUT","PATCH","DELETE","OPTIONS"}.contains(method))fail("unsupported workload HTTP method");
    auto target=text(row.get("path"),2048,false);
    if(target.front()!='/'||target.starts_with("//")||std::any_of(target.begin(),target.end(),[](unsigned char c){return c<33||c>126||c=='#'||c=='\\';}))fail("workload request requires a relative visible-ASCII HTTP target");
    (void)optionalText(row,"body","",65536);auto content=optionalText(row,"content_type","application/json",128);
    if(content.empty()||std::any_of(content.begin(),content.end(),[](unsigned char c){return c<32||c>126;}))fail("invalid workload content type");
    const auto &expected=object(row.get("expect"));keys(expected,{"status","text","sha256"});(void)integer(expected.get("status"),100,599);
    std::optional<std::string> body,digestValue;if(expected.get("text"))body=text(expected.get("text"),65536);
    if(expected.get("sha256")){digestValue=text(expected.get("sha256"),64);if(!digest(*digestValue))fail("invalid expected response SHA-256");}
    if(body&&digestValue&&sha(*body)!=*digestValue)fail("response text differs from its expected SHA-256");
  }
  llvm::json::Array normalized;int64_t iterations=optionalInteger(top,"warmup",0,0,128),warmup=iterations;
  for(const auto &value:*phases){const auto &row=object(&value);keys(row,{"concurrency","iterations"});auto concurrency=integer(row.get("concurrency"),1,64),count=integer(row.get("iterations"),1,4096);iterations+=concurrency*count;normalized.push_back(Object{{"concurrency",concurrency},{"iterations",count}});}
  auto total=iterations*int64_t(requests->size());if(total>4096)fail("workload exceeds4096 total requests");
  Value authorization=nullptr;if(top.get("authorization_env")){auto name=text(top.get("authorization_env"),128);if(!variable(name))fail("invalid authorization environment variable");authorization=std::move(name);}
  result.helper=resourceFile("tools/server_workload.py");result.helperSource=bounded(result.helper);result.helperSha256=sha(result.helperSource);
  result.plan=Object{{"schema","nex.server-workload-plan/1"},{"sha256",result.sha256},{"total_requests",total},{"request_definitions",int64_t(requests->size())},
    {"phases",std::move(normalized)},{"warmup",warmup},{"authorization_env",std::move(authorization)},
    {"request_timeout_ms",optionalInteger(top,"request_timeout_ms",1000,50,5000)},{"startup_timeout_ms",optionalInteger(top,"startup_timeout_ms",5000,50,15000)},
    {"loopback_only",true},{"connection_policy","one HTTP/1.1 connection per request; no redirect or retry"},{"authorization_values_captured",false},{"request_payloads_captured",false}};
  return result;
}
void validateServerWorkloadAuthority(const ServerWorkload &workload,const std::vector<std::string> &arguments,const std::map<std::string,std::string> &environment){
  for(const auto &argument:arguments)for(auto name:{"--host","--port","--cert","--key"})if(argument==name||argument.starts_with(std::string(name)+"="))fail("workload owns its loopback HTTP listener; host,port and TLS options are unsupported");
  if(auto name=workload.plan.getString("authorization_env")){
    auto override=environment.find(name->str());auto inherited=std::getenv(name->str().c_str());std::string value=override!=environment.end()?override->second:inherited?inherited:"";
    if(value.empty()||value.size()>8192||std::any_of(value.begin(),value.end(),[](unsigned char c){return !((c>='a'&&c<='z')||(c>='A'&&c<='Z')||(c>='0'&&c<='9')||std::string("._~+/=-").find(c)!=std::string::npos);}))fail("authorization environment value is unavailable or invalid","E_SERVER_WORKLOAD_AUTH");
  }
}
void verifyServerWorkloadInputs(const ServerWorkload &workload){
  std::error_code error;auto path=fs::canonical(workload.selection,error);
  if(error||path.string()!=workload.path||bounded(workload.selection)!=workload.source||bounded(workload.helper)!=workload.helperSource)fail("workload inputs changed after preflight","E_PROJECT_INPUT_CHANGED");
}
ServerWorkloadRun::ServerWorkloadRun(const ServerWorkload &inputWorkload):workload(inputWorkload){
  verifyServerWorkloadInputs(workload);auto executable=llvm::sys::findProgramByName(pythonProgram());if(!executable)throw Error("E_TOOL","server workload profiling requires Python3");python=*executable;
  directory=createTemporaryDirectory("nex-server-workload");input=(fs::path(directory)/"workload.json").string();result=(fs::path(directory)/"result.json").string();runner=(fs::path(directory)/"runner.py").string();
  try{writeFile(input,workload.source);writeFile(runner,workload.helperSource);}catch(...){fs::remove_all(directory);throw;}
}
ServerWorkloadRun::~ServerWorkloadRun(){std::error_code ignored;fs::remove_all(directory,ignored);}
std::vector<std::string> ServerWorkloadRun::launcher()const{return {python,"-B","-X","utf8",runner,"--workload",input,"--expected-hash",workload.sha256,"--result",result,"--"};}
Value ServerWorkloadRun::evidence()const{
  verifyServerWorkloadInputs(workload);auto parsed=llvm::json::parse(bounded(result));if(!parsed){llvm::consumeError(parsed.takeError());fail("workload runner produced invalid JSON");}
  auto value=parsed->getAsObject();auto planned=workload.plan.getInteger("total_requests");
  if(!value||value->getString("schema")!="nex.server-workload-result/1"||value->getString("definition_sha256")!=workload.sha256||value->getInteger("planned_requests")!=planned||!value->getBoolean("ok")||!value->getInteger("completed_requests")||*value->getInteger("completed_requests")<0||*value->getInteger("completed_requests")>*planned)fail("workload runner result does not match its pinned definition");
  (*value)["runner_sha256"]=workload.helperSha256;return std::move(*parsed);
}
}
