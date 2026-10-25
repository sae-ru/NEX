#include "nex_task_file_source.h"
#include <array>
#include <cstdlib>
#include <filesystem>
#include <fstream>
#include <iostream>
#include <optional>
#include <unistd.h>

using namespace nexrt;
namespace fs=std::filesystem;
void require(bool ok,const char *why){if(!ok)throw std::runtime_error(why);}
template<class F>void error(const char *code,F f){try{f();}catch(const DataError &e){require(e.code==code,"wrong diagnostic");return;}throw std::runtime_error("expected rejection");}
int main(){try{
  char path[]="/tmp/nex-file-regions-XXXXXX";auto *created=::mkdtemp(path);require(created,"mkdtemp failed");fs::path root(created);
  struct Cleanup{fs::path root;~Cleanup(){std::error_code e;fs::remove_all(root,e);}}cleanup{root};
  std::ofstream(root/"input",std::ios::binary)<<"abcdef";
  TextFiles files(root.string(),true);FileScope scope(files);auto reads=captureFileReadGrant(false);
  size_t cases=0;auto run=[&](const char *name,auto body){body();++cases;std::cout<<"PASS "<<name<<'\n';};
  for(auto family:{ResourceRegionFamily::Native,ResourceRegionFamily::Reference}){
    run("bound owner requires explicit genuine actor",[&]{
      ResourceRegion region(family),foreign(family);auto child=region.child();auto actor=region.authority();
      auto file=reads.openRead("input").openInRegion(actor);
      error("E_RESOURCE_SCOPE",[&]{file.lease();});error("E_RESOURCE_SCOPE",[&]{file.leaseInRegion(foreign.authority());});
      auto borrow=file.leaseInRegion(child.authority());require(borrow.read(2)==std::vector<uint8_t>({'a','b'}),"descendant read differs");
      child.close();error("E_RESOURCE_SCOPE",[&]{borrow.read(1);});require(file.isOpen(),"borrower closure closed ancestor file");file.close();
    });
    run("logical close waits exact physical file lease",[&]{
      ResourceRegion region(family);auto file=reads.openRead("input").openInRegion(region.authority());
      std::optional<FileStreamLease> pin(file.leaseInRegion(region.authority()));auto retirement=region.beginClose();retirement.requestClose();
      require(!file.isOpen()&&!retirement.ready(),"owner published physical completion too early");
      error("E_RESOURCE_SCOPE",[&]{pin->read(1);});pin.reset();require(retirement.ready(),"file retirement did not settle");
    });
    run("failed in-progress construction retires creation fence",[&]{
      ResourceRegion region(family);auto actor=region.authority();std::optional<ResourceRegionRetirement> retirement;bool sawPending=false;
      error("E_RESOURCE_SCOPE",[&]{reads.openRead("input").openInRegion(actor,[&]{if(!retirement){retirement.emplace(region.beginClose());retirement->requestClose();sawPending=!retirement->ready();}});});
      require(sawPending&&retirement->ready(),"failed open lost creation settlement");
      std::vector<FileResource> all;for(size_t i=0;i<64;++i)all.push_back(reads.openRead("input").open());
      error("E_RESOURCE_LIMIT",[&]{reads.openRead("input").open();});
    });
  }
  run("request ancestor promotion survives scheduler retirement",[&]{
    ResourceRegion request(ResourceRegionFamily::Request);auto native=ResourceRegion::inRequest(ResourceRegionFamily::Native,request.authority());
    auto reference=ResourceRegion::inRequest(ResourceRegionFamily::Reference,request.authority());
    auto file=reads.openRead("input").openInRegion(native.authority());
    FileResource::transferRegions(std::span<const FileResource>(&file,1),native.authority(),request.authority());
    native.close();require(file.isOpen(),"promoted file died with original scheduler");
    auto lease=file.leaseInRegion(reference.authority());require(lease.read(1)==std::vector<uint8_t>({'a'}),"common request borrower failed");
    auto close=request.beginClose();close.requestClose();require(!close.ready(),"promoted physical lease was not retained");lease={};require(close.ready(),"request physical close did not finish");
  });
  auto external=[&](ResourceDomain &physical,const ResourceRegionAuthority &actor){
    ExternalResourceType<int> type("file_regions::Probe",std::string(64,'a'));ResourceByteBudget budget(8);std::array<ResourceByteBudget,1> budgets{budget};
    return ExternalResource::makeInRegion(physical.access(),actor,type,budgets,4,std::make_shared<int>(0),{},[](const ResourcePermit&){return std::make_unique<int>(1);});
  };
  run("mixed capacity failure promotes no owner",[&]{
    ResourceRegionLimits bounds;bounds.owners=1;ResourceRegion request(ResourceRegionFamily::Request,bounds);
    auto region=ResourceRegion::inRequest(ResourceRegionFamily::Native,request.authority());ResourceDomain physical(4);
    auto f=reads.openRead("input").openInRegion(region.authority());auto object=external(physical,region.authority());
    error("E_RESOURCE_REGION_LIMIT",[&]{ExternalResource::transferRegions(std::span<const ExternalResource>(&object,1),region.authority(),request.authority(),true,std::span<const FileResource>(&f,1));});
    region.close();require(!object.isOpen()&&!f.isOpen(),"mixed failed batch partially promoted an owner");require(physical.used()==0,"external quota remained after mixed failure");
  });
  run("mixed successful batch preserves both owners",[&]{
    ResourceRegion root;auto child=root.child();ResourceDomain physical(4);
    auto f=reads.openRead("input").openInRegion(child.authority());auto object=external(physical,child.authority());
    ExternalResource::transferRegions(std::span<const ExternalResource>(&object,1),child.authority(),root.authority(),true,std::span<const FileResource>(&f,1));
    child.close();require(f.isOpen()&&object.isOpen(),"mixed success did not preserve aliases");
    root.close();require(!f.isOpen()&&!object.isOpen()&&physical.used()==0,"mixed root failed to retire owners");
  });
  run("unscoped legacy file cannot fabricate logical ownership",[&]{
    ResourceRegion region;auto file=reads.openRead("input").open();
    error("E_RESOURCE_SCOPE",[&]{FileResource::transferRegions(std::span<const FileResource>(&file,1),region.authority(),region.authority());});
    require(file.isOpen(),"rejected legacy transfer changed the file");
  });
  run("open checkpoint may destroy its originating lease",[&]{
    ResourceRegion region;auto lease=std::make_unique<FileOpenLease>(reads.openRead("input"));
    auto file=lease->openInRegion(region.authority(),[&]{lease.reset();});require(file.isOpen(),"lease callback destroyed opened file");file.close();
  });
  run("final admission checkpoint cannot revive a revoked owner",[&]{
    ResourceRegion region;auto actor=region.authority();auto file=reads.openRead("input").openInRegion(actor);
    auto work=PreparedTaskFileStream::read(file,2,actor);auto raw=work.operation()->run(TaskExternalControl{});unsigned polls=0;
    error("E_RESOURCE_SCOPE",[&]{work.admit(std::move(raw),[&]{if(++polls==2)region.close();});});
  });
  std::cout<<"{\"ok\":true,\"file_region_cases\":"<<cases<<",\"public_source_support\":false}\n";return 0;
}catch(const std::exception &e){std::cerr<<e.what()<<'\n';return 1;}}
