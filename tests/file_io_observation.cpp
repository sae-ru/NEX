#include "nex_files.h"
#include "nex_task_file_stream.h"
#include <chrono>
#include <filesystem>
#include <fstream>
#include <iostream>
#include <optional>
#include <stdexcept>
using namespace nexrt;
namespace fs=std::filesystem;
namespace {
void require(bool value,const char *message){if(!value)throw std::runtime_error(message);}
template<class F>void rejects(const std::string &code,F action){try{action();}catch(const DataError &e){require(e.code==code,"unexpected file host diagnostic");return;}throw std::runtime_error("file host operation unexpectedly succeeded");}
std::string read(const fs::path &p){std::ifstream stream(p,std::ios::binary);return {std::istreambuf_iterator<char>(stream),{}};}
void write(const fs::path &p,const std::string &text){std::ofstream stream(p,std::ios::binary);stream<<text;}
}
int main(){try{
 auto root=fs::canonical(fs::temp_directory_path())/("nex-file-observation-"+std::to_string(std::chrono::steady_clock::now().time_since_epoch().count()));require(fs::create_directory(root),"cannot create file observer fixture");
 struct Cleanup {fs::path root;~Cleanup(){fs::remove_all(root);}} cleanup{root};write(root/"input","abcdef");write(root/"output","original");size_t cases=0;
 {
  TextFiles files(root.string(),true);auto f=files.open("input",FileMode::Read);auto bytes=f.read(3);require(std::string(reinterpret_cast<const char*>(bytes.view().data()),bytes.view().size())=="abc","default observer changed read");require(f.close()&&!f.close(),"default observer changed close");++cases;
 }
 {
  std::optional<FileResource> f;bool observed=false;TextFiles files(root.string(),true,[&](const FileIOEvent &event){if(event.operation==FileIOOperation::Read&&event.phase==FileIOPhase::After){observed=true;require(event.result==3&&event.error==0,"read observer lacks actual syscall result");require(f->close(),"reentrant close failed");}});
  auto domain=files.resourceScope(1);f=files.openIn(domain,"input",FileMode::Read);rejects("E_RESOURCE_CLOSED",[&]{f->read(3);});require(observed&&domain.used()==0,"reentrant close did not retire physical lease");++cases;
 }
 {
  ResourceDomain *selected=nullptr;bool after=false;TextFiles files(root.string(),true,[&](const FileIOEvent &event){if(event.operation!=FileIOOperation::Write)return;if(event.phase==FileIOPhase::Before)selected->revoke();else after=true;});
  auto domain=files.resourceScope(1);selected=&domain;auto f=files.openIn(domain,"output",FileMode::Append);rejects("E_RESOURCE_SCOPE",[&]{f.write(ByteBuffer::copy(std::span<const uint8_t>(reinterpret_cast<const uint8_t*>("!"),1)));});require(!after&&read(root/"output")=="original"&&domain.used()==0,"revoked before-write observer allowed IO");++cases;
 }
 {
  ResourceDomain *selected=nullptr;TextFiles files(root.string(),true,[&](const FileIOEvent &event){if(event.operation==FileIOOperation::OpenWrite&&event.phase==FileIOPhase::Before)selected->revoke();});
  auto domain=files.resourceScope(1);selected=&domain;rejects("E_RESOURCE_SCOPE",[&]{files.openIn(domain,"output",FileMode::WriteTruncate);});require(read(root/"output")=="original"&&domain.used()==0,"revoked before-open observer allowed truncation");++cases;
 }
 {
  TextFiles a(root.string(),true),b(root.string(),true);auto unrelated=b.resourceScope(1);FileScope valid(a);
  rejects("CAPABILITY",[&]{FileScope invalid(a,unrelated);});auto grant=captureFileReadGrant(false);require(grant.lease("input").read().size()==6,"wrong-scope refusal corrupted lexical grant");++cases;
 }
 {
  TextFiles files(root.string(),true);auto domain=files.resourceScope(1);FileScope scope(files,domain);auto f=fileOpen("input",FileMode::Read,false);
  rejects("E_RESOURCE_LIMIT",[&]{fileOpen("input",FileMode::Read,false);});require(domain.used()==1&&f.close()&&domain.used()==0,"explicit domain quota differs");auto next=fileOpen("input",FileMode::Read,false);require(next.close(),"settled quota not reusable");++cases;
 }
 {
  TextFiles files(root.string(),true);auto domain=files.resourceScope(1);FileScope scope(files,domain);auto grant=captureFileReadGrant(false);domain.revoke();rejects("E_RESOURCE_SCOPE",[&]{grant.check();});require(domain.used()==0,"revoked captured grant acquired quota");++cases;
 }
 {
  size_t events=0;TextFiles files(root.string(),false,[&](const FileIOEvent &){++events;});auto domain=files.resourceScope(1);FileScope scope(files,domain);
  rejects("CAPABILITY",[&]{fileOpen("output",FileMode::WriteTruncate,false);});require(events==0&&domain.used()==0&&read(root/"output")=="original","scoped observer upgraded readonly grant");++cases;
 }
 {
  bool observed=false;TextFiles files(root.string(),true,[&](const FileIOEvent &event){if(event.operation==FileIOOperation::Read&&event.phase==FileIOPhase::After){observed=true;throw std::runtime_error("explicit trusted observer failure");}});auto domain=files.resourceScope(1);auto f=files.openIn(domain,"input",FileMode::Read);
  rejects("E_TASK_HOST",[&]{f.read(3);});
  require(observed&&f.close()&&domain.used()==0,"observer exception retained the physical file");++cases;
 }
 {
  ResourceDomain *selected=nullptr;TextFiles files(root.string(),true,[&](const FileIOEvent &event){if(event.operation==FileIOOperation::Read&&event.phase==FileIOPhase::After)selected->revoke();});auto domain=files.resourceScope(1);selected=&domain;auto f=files.openIn(domain,"input",FileMode::Read);
  {auto prepared=PreparedTaskFileStream::read(f,3);TaskExternalResult raw;bool failed=false;
   try{prepared.operation()->run(TaskExternalControl{});}catch(const DataError &e){failed=true;require(e.code=="E_RESOURCE_SCOPE","physical read lost revocation");raw.errorCode=e.code;raw.errorMessage=e.what();}
   require(failed,"revoked physical read succeeded");rejects("E_RESOURCE_SCOPE",[&]{prepared.admit(raw);});rejects("E_TASK_STATE",[&]{prepared.admit(raw);});
  }
  require(domain.used()==0,"failed stream admission retained its physical quota");++cases;
 }
 {
  ResourceDomain *selected=nullptr;TextFiles files(root.string(),true,[&](const FileIOEvent &event){if(event.operation==FileIOOperation::OpenRead&&event.phase==FileIOPhase::After)selected->revoke();});auto domain=files.resourceScope(1);selected=&domain;auto cleanup=std::make_shared<ResourceExecutor>();
  {FileScope scope(files,domain);auto grant=captureFileReadGrant(false);PreparedTaskFileOpen prepared(grant.openRead("input"),{},cleanup);TaskExternalResult raw;bool failed=false;
   try{prepared.operation()->run(TaskExternalControl{});}catch(const DataError &e){failed=true;require(e.code=="E_RESOURCE_SCOPE","physical open lost revocation");raw.errorCode=e.code;raw.errorMessage=e.what();}
   require(failed,"revoked physical open succeeded");rejects("E_RESOURCE_SCOPE",[&]{prepared.admit(raw);});rejects("E_TASK_STATE",[&]{prepared.admit(raw);});
  }
  cleanup->drain();require(domain.used()==0&&cleanup->stats().resources==0,"failed open admission retained cleanup/quota");cleanup->finish();++cases;
 }
 std::cout<<"{\"ok\":true,\"file_observer_cases\":"<<cases<<",\"no_authority_reconstruction\":true,\"reentrant_callbacks_outside_cursor_locks\":true}\n";return 0;
}catch(const std::exception &e){std::cerr<<e.what()<<'\n';return 1;}}
