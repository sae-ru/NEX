#include "nex_files.h"
#include <atomic>
#include <barrier>
#include <filesystem>
#include <fstream>
#include <iostream>
#include <set>
#include <thread>
#include <fcntl.h>
#include <sys/stat.h>
#include <unistd.h>

namespace fs=std::filesystem;
using namespace nexrt;
namespace {
void require(bool value,const std::string &message){if(!value)throw std::runtime_error(message);}
template<class F> void error(const std::string &code,F call){
  try{call();}catch(const DataError &caught){require(caught.code==code,"expected "+code+", got "+caught.code);return;}
  throw std::runtime_error("expected "+code);
}
struct Stats {std::atomic<int> live{0},destroyed{0};};
struct Probe {
  Stats &stats;
  std::function<void()> onDestroy;
  Probe(Stats &stats,std::function<void()> onDestroy={}):stats(stats),onDestroy(std::move(onDestroy)){++stats.live;}
  ~Probe() noexcept {if(onDestroy)onDestroy();--stats.live;++stats.destroyed;}
};
auto probe(ResourceDomain &domain,Stats &stats){return domain.make<Probe>([&](const ResourcePermit &permit){permit.check();return std::make_unique<Probe>(stats);});}
ByteBuffer binary(std::string_view text){return ByteBuffer::copy({reinterpret_cast<const uint8_t*>(text.data()),text.size()});}
std::string text(const ByteBuffer &bytes){auto view=bytes.view();return view.empty()?std::string():std::string(reinterpret_cast<const char*>(view.data()),view.size());}
void raw(const fs::path &path,const std::string &value){std::ofstream stream(path,std::ios::binary);stream.write(value.data(),value.size());require(bool(stream),"fixture write failed");}
int descriptors(){int count=0;for(int fd=0;fd<1024;++fd)if(::fcntl(fd,F_GETFD)>=0)++count;return count;}
struct Fixture {
  fs::path directory;
  Fixture(){auto pattern=(fs::temp_directory_path()/"nex-resources-XXXXXX").string();auto *p=::mkdtemp(pattern.data());require(p,"cannot create fixture");directory=fs::canonical(p);}
  ~Fixture(){std::error_code error;fs::remove_all(directory,error);}
};
}
int main(){
  try{
    unsigned cases=0;auto run=[&](const char *name,const auto &call){call();++cases;std::cout<<"PASS "<<name<<std::endl;};
    run("aliases close once with stable identities",[]{
      Stats stats;ResourceDomain domain;auto a=probe(domain,stats),b=a;auto id=a.identity();
      require(id&&id==b.identity()&&a.isOpen()&&domain.used()==1,"identity/alias mismatch");
      require(a.close()&&!b.close()&&!b.isOpen()&&stats.destroyed==1&&domain.used()==0,"close not shared/idempotent");
      error("E_RESOURCE_CLOSED",[&]{b.acquire();});auto c=probe(domain,stats);require(c.identity()!=id,"identity reused");
    });
    run("lease pins physical quota after logical close",[]{
      Stats stats;ResourceDomain domain(1);auto owner=probe(domain,stats);auto lease=owner.acquire();owner.close();
      require(stats.live==1&&domain.used()==1,"in-flight payload was destroyed");
      error("E_RESOURCE_CLOSED",[&]{lease.check();});int factories=0;
      error("E_RESOURCE_LIMIT",[&]{domain.make<Probe>([&](const auto &){++factories;return std::make_unique<Probe>(stats);});});
      require(!factories,"quota checked after side effect");lease={};require(stats.live==0&&domain.used()==0,"lease leaked slot");
      require(probe(domain,stats).isOpen(),"released quota unusable");
    });
    run("dropping last owner closes payload",[]{
      Stats stats;ResourceDomain domain;
      {auto a=probe(domain,stats);{auto b=a;require(stats.live==1,"alias copied payload");}require(a.isOpen(),"alias drop closed owner");}
      require(stats.live==0&&stats.destroyed==1&&domain.used()==0,"last owner leaked");
    });
    run("escaped leases cannot bypass ancestor revocation",[]{
      Stats stats;ResourceDomain root(2);auto child=root.child(2);auto leaf=child.child(2);auto a=probe(leaf,stats);auto lease=a.acquire();
      require(root.used()==1&&child.used()==1&&leaf.used()==1,"ancestor quota not bound");root.revoke();
      require(!a.isOpen()&&stats.live==1,"scope failed logical/physical separation");
      error("E_RESOURCE_SCOPE",[&]{a.acquire();});error("E_RESOURCE_SCOPE",[&]{lease.check();});
      error("E_RESOURCE_SCOPE",[&]{probe(child,stats);});lease={};require(root.used()==0&&stats.live==0,"ancestor resource leaked");
    });
    run("child quota and parent quota both apply",[]{
      Stats stats;ResourceDomain root(2);auto child=root.child(1);auto a=probe(child,stats);
      error("E_RESOURCE_LIMIT",[&]{probe(child,stats);});auto b=probe(root,stats);error("E_RESOURCE_LIMIT",[&]{probe(root,stats);});
      child.revoke();require(b.isOpen()&&!a.isOpen()&&root.used()==1,"child revoked unrelated resource");
    });
    run("domain destruction and move replacement revoke",[]{
      Stats stats;ResourceOwner<Probe> escaped;
      {ResourceDomain domain;escaped=probe(domain,stats);}require(!escaped.isOpen()&&stats.destroyed==1,"scope escape retained authority");
      ResourceDomain first,second;auto a=probe(first,stats),b=probe(second,stats);first=std::move(second);
      require(!a.isOpen()&&b.isOpen(),"move failed ownership transfer");error("E_RESOURCE_SCOPE",[&]{probe(second,stats);});
    });
    run("factory failure rolls back physical reservations",[]{
      Stats stats;ResourceDomain domain(1);
      try{domain.make<Probe>([&](const auto &)->std::unique_ptr<Probe>{auto value=std::make_unique<Probe>(stats);throw std::runtime_error("factory");});}
      catch(const std::runtime_error &caught){require(std::string(caught.what())=="factory","wrong factory exception");}
      require(stats.live==0&&stats.destroyed==1&&domain.used()==0,"factory leaked payload or quota");
      error("E_RESOURCE_CLOSED",[&]{domain.make<Probe>([](const auto &){return std::unique_ptr<Probe>();});});
      require(domain.used()==0,"null factory leaked quota");
    });
    run("revocation racing factory publication closes exactly once",[]{
      Stats stats;ResourceDomain domain;std::barrier checkpoint(2);std::atomic<bool> rejected=false;
      std::thread worker([&]{
        try{domain.make<Probe>([&](const auto &){auto p=std::make_unique<Probe>(stats);checkpoint.arrive_and_wait();checkpoint.arrive_and_wait();return p;});}
        catch(const DataError &caught){rejected=caught.code=="E_RESOURCE_SCOPE";}
      });
      checkpoint.arrive_and_wait();domain.revoke();checkpoint.arrive_and_wait();worker.join();
      require(rejected&&stats.live==0&&stats.destroyed==1&&domain.used()==0,"revoked factory published or leaked");
    });
    run("factory can destroy its domain wrapper",[]{
      Stats stats;auto domain=std::make_unique<ResourceDomain>();
      error("E_RESOURCE_SCOPE",[&]{domain->make<Probe>([&](const auto &permit){domain.reset();permit.check();return std::make_unique<Probe>(stats);});});
      require(!stats.live,"destroyed factory domain leaked");
    });
    run("retained access cannot extend domain authority",[]{
      Stats stats;ResourceAccess access;
      {ResourceDomain domain;access=domain.access();auto value=access.make<Probe>([&](const auto &permit){permit.check();return std::make_unique<Probe>(stats);});require(value.isOpen(),"retained access lost live authority");}
      int entered=0;error("E_RESOURCE_SCOPE",[&]{access.make<Probe>([&](const auto &){++entered;return std::make_unique<Probe>(stats);});});
      error("E_RESOURCE_SCOPE",[&]{access.check();});require(!entered&&!stats.live,"expired access ran factory");
      error("E_RESOURCE_SCOPE",[]{ResourceAccess().check();});
    });
    run("retained access enforces joined quotas and survives wrapper deletion",[]{
      Stats stats;ResourceDomain first(1),second(2);auto joined=std::make_unique<ResourceDomain>(first.combine(second));auto access=joined->access();
      auto owner=access.make<Probe>([&](const auto &){return std::make_unique<Probe>(stats);});auto lease=owner.acquire();owner.close();
      error("E_RESOURCE_LIMIT",[&]{access.make<Probe>([&](const auto &){return std::make_unique<Probe>(stats);});});
      joined.reset();error("E_RESOURCE_SCOPE",[&]{access.check();});require(stats.live==1&&first.used()==1&&second.used()==1,"access lost physical lease quota");
      lease={};require(!stats.live&&!first.used()&&!second.used(),"retained access leaked physical quota");
    });
    run("payload cleanup re-enters domain without locks",[]{
      Stats stats;ResourceDomain domain(1);std::atomic<bool> callback=false;
      auto a=domain.make<Probe>([&](const auto &){return std::make_unique<Probe>(stats,[&]{
        try{probe(domain,stats);}catch(const DataError &e){callback=e.code=="E_RESOURCE_SCOPE";}
      });});domain.revoke();require(callback&&stats.destroyed==1,"cleanup re-entry did not finish");
    });
    run("registry pruning races last-owner destruction",[]{
      Stats stats;ResourceDomain domain(32);std::atomic<bool> failed=false;
      auto work=[&]{try{for(int i=0;i<1500;++i){auto a=probe(domain,stats);if(i%2)a.close();}}catch(...){failed=true;}};
      std::thread a(work),b(work);a.join();b.join();
      require(!failed&&stats.live==0&&stats.destroyed==3000&&domain.used()==0,"registry race leaked or deadlocked");
    });
    run("bounded hierarchy and invalid quotas",[]{
      error("E_RESOURCE_LIMIT",[]{ResourceDomain d(0);});error("E_RESOURCE_LIMIT",[]{ResourceDomain d(4097);});
      std::vector<ResourceDomain> chain;chain.emplace_back();for(int i=1;i<8;++i)chain.push_back(chain.back().child());
      error("E_RESOURCE_LIMIT",[&]{chain.back().child();});
    });

    Fixture fixture;auto root=fixture.directory/"root",outside=fixture.directory/"outside";fs::create_directories(root/"nested");fs::create_directory(outside);
    raw(root/"input",std::string("A\0",2)+"Я🧠");raw(outside/"private","unchanged");TextFiles files(root.string(),true),readonly(root.string(),false);
    run("streamed bytes, aliases, cursor, EOF and seek",[&]{
      auto file=files.open("input",FileMode::Read),alias=file;require(file.identity()==alias.identity(),"file alias identity differs");
      require(text(file.read(2))==std::string("A\0",2)&&text(alias.read(64))=="Я🧠","shared cursor or bytes differ");
      require(file.read(1).length()==0&&file.size()==8,"EOF/size differs");require(file.seek(2)==2&&text(alias.read(64))=="Я🧠","seek differs");
      require(file.close()&&!alias.close(),"file close not aliased");error("E_RESOURCE_CLOSED",[&]{alias.read(0);});
    });
    run("truncation, bounded writes, append, flush and private creation",[&]{
      raw(root/"output","old trailing bytes");auto file=files.open("output",FileMode::WriteTruncate);require(file.size()==0,"not truncated");
      require(file.write(binary("abc"))==3,"write length differs");file.seek(1);require(file.write(binary("Z"))==1,"seek write differs");file.flush();file.close();
      auto append=files.open("output",FileMode::Append);append.seek(0);require(append.write(binary("!"))==1,"append length differs");append.close();
      require(text(files.open("output",FileMode::Read).read(100))=="aZc!","append ignored kernel end position");
      auto created=files.open("new-private",FileMode::WriteTruncate);struct stat info{};require(!::stat((root/"new-private").c_str(),&info)&&(info.st_mode&0777)==0600,"new mode not private");
    });
    run("mode permissions and closed zero-length operations",[&]{
      auto before=descriptors();error("CAPABILITY",[&]{readonly.open("denied",FileMode::WriteTruncate);});require(!fs::exists(root/"denied"),"denied create side effect");
      {auto file=files.open("input",FileMode::Read);error("CAPABILITY",[&]{file.write({});});error("CAPABILITY",[&]{file.flush();});}
      {auto file=files.open("output",FileMode::Append);error("CAPABILITY",[&]{file.read(0);});file.close();error("E_RESOURCE_CLOSED",[&]{file.write({});});}
      FileResource empty;error("E_RESOURCE_CLOSED",[&]{empty.seek(0);});require(descriptors()==before,"permission failure leaked FD");
    });
    run("stream argument and per-call byte limits",[&]{
      auto file=files.open("input",FileMode::Read);error("E_RANGE",[&]{file.read(-1);});error("LIMIT",[&]{file.read(TextFiles::byteLimit+1);});error("E_RANGE",[&]{file.seek(-1);});
      auto output=files.open("output",FileMode::Append);error("LIMIT",[&]{output.write(binary(std::string(TextFiles::byteLimit+1,'x')));});
      require(file.seek(0)==0&&file.read(0).length()==0,"zero read failed");
    });
    run("large files can be consumed in bounded chunks",[&]{
      std::string content(TextFiles::byteLimit+123,'x');raw(root/"large",content);auto file=files.open("large",FileMode::Read);
      require(file.read(TextFiles::byteLimit).length()==int64_t(TextFiles::byteLimit)&&file.read(1000).length()==123&&file.read(1).length()==0,"stream inherited whole-file size limit");
    });
    run("stream path and nonregular rejection without truncation",[&]{
      fs::create_symlink(outside/"private",root/"link");fs::create_directory_symlink(outside,root/"dir-link");require(!::mkfifo((root/"fifo").c_str(),0600),"mkfifo failed");auto baseline=descriptors();
      for(auto mode:{FileMode::Read,FileMode::WriteTruncate,FileMode::Append}){
        for(const auto &path:std::vector<std::string>{"../outside/private","/absolute","nested//bad","nested/../bad","link","dir-link/private","fifo","nested",std::string("bad\0name",8),std::string("\xff",1)})
          error(path==std::string("\xff",1)?"E_UTF8":"VALIDATION",[&]{files.open(path,mode);});
      }
      auto unchanged=TextFiles(outside.string(),false).readBytes("private");
      require(isSuccess(unchanged)&&text(byteBuffer(unwrap(unchanged).object))=="unchanged","outside changed");
      require(descriptors()==baseline,"rejected stream leaked descriptor");
    });
    run("physical quotas checked before file create/truncate",[&]{
      auto scope=files.resourceScope(1);auto file=files.openIn(scope,"input",FileMode::Read);raw(root/"keep","preserved");
      error("E_RESOURCE_LIMIT",[&]{files.openIn(scope,"not-created",FileMode::WriteTruncate);});error("E_RESOURCE_LIMIT",[&]{files.openIn(scope,"keep",FileMode::WriteTruncate);});
      require(!fs::exists(root/"not-created")&&text(files.open("keep",FileMode::Read).read(100))=="preserved","quota failure touched path");
      ResourceDomain unrelated;error("CAPABILITY",[&]{files.openIn(unrelated,"input",FileMode::Read);});
    });
    run("scope escape and environment reset revoke handles",[&]{
      FileResource escaped;auto baseline=descriptors();
      {FileScope scope(files);escaped=fileOpen("input",FileMode::Read,false);require(escaped.isOpen(),"explicit grant missing");}
      error("E_RESOURCE_SCOPE",[&]{escaped.read(0);});require(descriptors()==baseline,"request scope leaked FD");
      ::setenv("NEX_FILES_ROOT",root.c_str(),1);resetFileEnvironment();auto env=fileOpen("input",FileMode::Read);resetFileEnvironment();
      error("E_RESOURCE_SCOPE",[&]{env.size();});::unsetenv("NEX_FILES_ROOT");
      error("CAPABILITY",[&]{FileScope denied(false);fileOpen("input",FileMode::Read);});
    });
    run("retained host grant survives original service destruction",[&]{
      auto service=std::make_unique<TextFiles>(root.string(),false);FileScope scope(*service);service.reset();
      require(text(fileOpen("input",FileMode::Read,false).read(2))==std::string("A\0",2),"scope retained dangling service");
    });
    run("destroyed capability revokes direct file handles",[&]{
      auto service=std::make_unique<TextFiles>(root.string(),false);auto file=service->open("input",FileMode::Read);service.reset();
      error("E_RESOURCE_SCOPE",[&]{file.read(0);});
    });
    run("callbacks can close handles and release caller arguments",[&]{
      auto file=files.open("input",FileMode::Read);auto baseline=descriptors();
      error("E_RESOURCE_CLOSED",[&]{file.read(1,[&]{file.close();require(descriptors()==baseline,"closed in-flight descriptor reused early");});});
      require(descriptors()==baseline-1,"closed lease leaked descriptor");
      auto output=files.open("callback-bytes",FileMode::WriteTruncate);auto content=binary(std::string(160000,'b'));FileResource::Poll poll;
      poll=[&]{content={};poll={};};require(output.write(content,poll)==160000,"callback released borrowed bytes/function");
      require(text(files.open("callback-bytes",FileMode::Read).read(200000))==std::string(160000,'b'),"callback write data changed");
    });
    run("callbacks can destroy wrapper and request scope",[&]{
      auto file=std::make_unique<FileResource>(files.open("input",FileMode::Read));require(text(file->read(2,[&]{file.reset();}))==std::string("A\0",2),"active lease depended on wrapper");
      auto scope=std::make_unique<FileScope>(files);auto escaped=fileOpen("input",FileMode::Read,false);
      error("E_RESOURCE_SCOPE",[&]{escaped.read(1,[&]{scope.reset();});});
    });
    run("cancel before and after write has documented effects",[&]{
      auto output=files.open("canceled",FileMode::WriteTruncate);unsigned polls=0;
      try{output.write(binary("before"),[]{throw std::runtime_error("cancel");});}catch(const std::runtime_error &e){require(std::string(e.what())=="cancel","wrong cancel");}
      require(output.size()==0,"pre-write cancellation wrote bytes");
      try{output.write(binary("after"),[&]{if(++polls==2)throw std::runtime_error("cancel");});}catch(const std::runtime_error &e){require(std::string(e.what())=="cancel","wrong cancel");}
      require(output.size()==5&&polls==2,"post-write cancellation claimed rollback");
    });
    run("open cancellation releases descriptors and reserved quota",[&]{
      auto scope=files.resourceScope(1);auto baseline=descriptors();
      for(unsigned stop=1;stop<=3;++stop){unsigned polls=0;
        try{files.openIn(scope,"input",FileMode::Read,[&]{if(++polls==stop)throw std::runtime_error("cancel");});}
        catch(const std::runtime_error &e){require(std::string(e.what())=="cancel","wrong open cancel");}
        require(scope.used()==0&&descriptors()==baseline,"canceled open leaked FD or quota");
      }
      auto request=std::make_unique<FileScope>(files);unsigned polls=0;
      error("E_RESOURCE_SCOPE",[&]{fileOpen("input",FileMode::Read,false,[&]{if(++polls==3)request.reset();});});
      require(descriptors()==baseline,"revoked factory leaked FD");
    });
    run("concurrent aliases consume one serialized cursor",[&]{
      raw(root/"cursor",std::string(2000,'x'));auto file=files.open("cursor",FileMode::Read);std::atomic<int64_t> count=0;std::atomic<bool> failed=false;
      auto work=[&,alias=file]{try{for(;;){auto bytes=alias.read(17);if(!bytes.length())break;count+=bytes.length();}}catch(...){failed=true;}};
      std::thread a(work),b(work),c(work);a.join();b.join();c.join();require(!failed&&count==2000,"aliases duplicated or lost cursor bytes");
    });
    run("poll callback can re-enter the same cursor",[&]{
      auto file=files.open("input",FileMode::Read);bool entered=false;
      auto read=file.read(64,[&]{if(!entered){entered=true;require(text(file.read(2))==std::string("A\0",2),"nested read differs");}});
      require(entered&&text(read)=="Я🧠","re-entrant cursor state differs");
    });
    run("whole-file callback retains service, text, path and callback",[&]{
      auto service=std::make_unique<TextFiles>(root.string(),true);std::string path="whole-callback",content(150000,'q');TextFiles::Poll poll;
      poll=[&]{service.reset();path="../bad";content="changed";poll={};};auto result=service->write(path,content,poll);
      require(isSuccess(result)&&text(files.open("whole-callback",FileMode::Read).read(200000))==std::string(150000,'q'),"whole-file borrowed input changed");
      service=std::make_unique<TextFiles>(root.string(),false);path="input";
      auto read=service->readBytes(path,[&]{service.reset();path="missing";});require(isSuccess(read)&&byteBuffer(unwrap(read).object).length()==8,"whole-file read depended on caller lifetime");
    });
    std::cout<<"resource ownership and streaming files: "<<cases<<" cases passed\n";return 0;
  }catch(const std::exception &caught){std::cerr<<caught.what()<<'\n';return 1;}
}
