#include "nex/task_package.h"
#include "llvm/Support/Error.h"
#include <algorithm>
#include <filesystem>
#include <map>
#include <set>

namespace nex {
namespace {
namespace fs=std::filesystem;
using JSON=llvm::json::Value;using Object=llvm::json::Object;using Array=llvm::json::Array;
[[noreturn]] void fail(const std::string &message){throw Error("E_TASK_NOTICES",message);}
const Object &object(const JSON &value){auto p=value.getAsObject();if(!p)fail("notice data requires objects");return *p;}
void fields(const Object &o,std::initializer_list<const char*> names){for(const auto &[key,_]:o)if(std::none_of(names.begin(),names.end(),[&](auto name){return key==name;}))fail("unknown notice field: "+key.str());}
std::string text(const Object &o,const char *key){auto s=o.getString(key);if(!s||s->empty()||s->size()>8192||s->contains('\0')||!llvm::json::isUTF8(*s))fail(std::string("invalid notice string: ")+key);return s->str();}
const Array &array(const Object &o,const char *key,size_t maximum){auto a=o.getArray(key);if(!a||a->empty()||a->size()>maximum)fail(std::string("invalid notice inventory: ")+key);return *a;}
bool within(const fs::path &path,const fs::path &root){auto r=path.lexically_relative(root);return !r.is_absolute()&&std::none_of(r.begin(),r.end(),[](auto p){return p=="..";});}
fs::path physical(const fs::path &path){std::error_code error;auto p=fs::canonical(path,error);if(error)fail("missing/inaccessible notice path: "+path.string());return p;}
std::string read(const fs::path &p,uint64_t max){if(!fs::is_regular_file(p)||fs::file_size(p)>max)fail("missing/oversized notice input: "+p.string());auto s=readFile(p.string());if(!llvm::json::isUTF8(s)||s.find('\0')!=std::string::npos)fail("notices require UTF-8 text without NUL");return s;}
JSON parse(const std::string &s){auto v=llvm::json::parse(s);if(!v)throw Error("E_JSON",llvm::toString(v.takeError()));return std::move(*v);}
bool licenseName(const std::string &name){auto s=llvm::StringRef(name);if(!s.consume_front("licenses/")||!s.consume_back(".txt")||s.empty()||s.size()>4)return false;return std::all_of(s.begin(),s.end(),[](char c){return c>='0'&&c<='9';});}
void validate(const JSON &snapshot){
  const auto &s=object(snapshot);fields(s,{"schema","catalogue","files"});if(s.getString("schema")!="nex.task-package-notices/1")fail("unsupported notice snapshot");
  auto c=s.getObject("catalogue"),files=s.getObject("files");if(!c||!files||files->empty()||files->size()>256)fail("invalid notice snapshot inventories");
  fields(*c,{"schema","components"});if(c->getString("schema")!="nex.sdk-notices/1")fail("expected nex.sdk-notices/1");
  std::set<std::string> names,used;uint64_t bytes=0;
  for(const auto &v:array(*c,"components",128)){
    const auto &item=object(v);fields(item,{"name","version","url","roots","license_files"});auto name=text(item,"name");
    if(name.size()>80||name=="."||name==".."||!names.insert(name).second||!std::all_of(name.begin(),name.end(),[](unsigned char ch){return (ch>='a'&&ch<='z')||(ch>='A'&&ch<='Z')||(ch>='0'&&ch<='9')||ch=='_'||ch=='-'||ch=='.';}))fail("invalid/duplicate notice component name");
    text(item,"version");text(item,"url");
    for(const auto &v:array(item,"roots",128)){auto p=v.getAsString();if(!p||p->empty()||p->size()>8192||p->contains('\0')||!fs::path(p->str()).is_absolute()||!llvm::json::isUTF8(*p))fail("notice roots require absolute paths");}
    for(const auto &v:array(item,"license_files",64)){auto p=v.getAsString();if(!p||!licenseName(p->str())||!files->getString(*p))fail("unindexed notice license");used.insert(p->str());}
  }
  if(used.size()!=files->size())fail("unreferenced notice license");
  for(const auto &[name,value]:*files){auto s=value.getAsString();if(!licenseName(name.str())||!s||s->size()>1048576||s->contains('\0')||!llvm::json::isUTF8(*s))fail("invalid notice license text");bytes+=s->size();}
  if(bytes>8*1048576||json(JSON(Object(*c))).size()+1>1048576||json(snapshot).size()+1>16*1048576)fail("notice snapshot exceeds its byte limit");
}
}
JSON captureTaskPackageNotices(const std::string &file,const std::string &projectRoot){
  auto root=physical(projectRoot),path=physical(file);if(!within(path,root))fail("task notice catalogue escapes its project");
  auto original=read(path,1048576);auto catalogue=parse(original);object(catalogue);auto &c=*catalogue.getAsObject();
  // Validate the input's envelope before normalizing paths into captured files.
  fields(c,{"schema","components"});if(c.getString("schema")!="nex.sdk-notices/1")fail("expected nex.sdk-notices/1");array(c,"components",128);
  Object files;std::map<std::string,std::string> captured;uint64_t bytes=0;
  for(auto &value:*c.getArray("components")){
    object(value);auto &item=*value.getAsObject();fields(item,{"name","version","url","roots","license_files"});array(item,"roots",128);array(item,"license_files",64);
    for(auto &value:*item.getArray("roots")){auto name=value.getAsString();if(!name||name->empty()||name->size()>8192||name->contains('\0'))fail("invalid notice root");value=physical(path.parent_path()/name->str()).string();}
    for(auto &value:*item.getArray("license_files")){
      auto name=value.getAsString();if(!name||name->empty()||name->size()>8192||name->contains('\0'))fail("invalid license path");auto source=physical(path.parent_path()/name->str());
      if(!within(source,root))fail("task license input escapes its project");
      auto found=captured.find(source.string());
      if(found==captured.end()){
        auto data=read(source,1048576);bytes+=data.size();if(bytes>8*1048576||files.size()>=256)fail("notice input limit exceeded");
        auto id="licenses/"+std::to_string(files.size())+".txt";files[id]=std::move(data);found=captured.emplace(source.string(),id).first;
      }value=found->second;
    }
  }
  if(read(path,1048576)!=original)fail("notice catalogue changed during capture");
  for(const auto &[source,name]:captured)if(read(source,1048576)!=files.getString(name)->str())fail("license changed during capture");
  JSON result=Object{{"schema","nex.task-package-notices/1"},{"catalogue",std::move(catalogue)},{"files",std::move(files)}};validate(result);return result;
}
std::string taskPackageNoticesHash(const JSON &snapshot){validate(snapshot);return hash(json(snapshot,false));}
JSON describeTaskPackageNotices(const JSON &snapshot){
  auto digest=taskPackageNoticesHash(snapshot);Array names;uint64_t bytes=0;const auto &s=object(snapshot);
  for(const auto &v:*s.getObject("catalogue")->getArray("components"))names.push_back(text(object(v),"name"));
  for(const auto &[_,v]:*s.getObject("files"))bytes+=v.getAsString()->size();
  return Object{{"schema","nex.task-package-notices-description/1"},{"ok",true},{"inputs_hash",digest},{"components",std::move(names)},{"license_files",s.getObject("files")->size()},{"license_bytes",int64_t(bytes)},{"external_tools_invoked",false},{"graph_store_opened",false}};
}
void saveTaskPackageNotices(const JSON &snapshot,const std::string &directory){
  validate(snapshot);fs::path base(directory);fs::create_directories(base);writeFile((base/"snapshot.json").string(),json(snapshot)+"\n");
  writeFile((base/"notices.json").string(),json(*object(snapshot).get("catalogue"))+"\n");
  for(const auto &[path,value]:*object(snapshot).getObject("files"))writeFile((base/path.str()).string(),value.getAsString()->str());
}
void verifyTaskPackageNotices(const JSON &snapshot,const std::string &directory){
  validate(snapshot);auto base=fs::canonical(directory);auto checked=[&](const fs::path &p,uint64_t maximum){auto actual=fs::canonical(p);if(actual!=p)fail("saved notice input is a symlink");return read(actual,maximum);};
  if(parse(checked(base/"snapshot.json",16*1048576))!=snapshot||parse(checked(base/"notices.json",1048576))!=*object(snapshot).get("catalogue"))fail("saved notice metadata changed");
  for(const auto &[path,value]:*object(snapshot).getObject("files"))if(checked(base/path.str(),1048576)!=value.getAsString()->str())fail("saved license changed");
}
}
