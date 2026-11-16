#include "host_test.h"
#include "host_file_observers.h"
#include "nex_cells.h"
#include "nex_files.h"
#include <filesystem>
#include <fstream>
#include <functional>
#include <iostream>
#include <fcntl.h>
#include <cstdlib>
#include <unistd.h>
using namespace nexrt;
namespace {
void require(bool ok,const char *message){if(!ok)throw std::runtime_error(message);}
template<class F>void rejects(const char *code,F body){
  try{body();}catch(const DataError &error){require(error.code==code,"wrong owned-cell diagnostic");return;}
  throw std::runtime_error("expected owned-cell diagnostic");
}
size_t descriptors(){
#ifdef _WIN32
  return nex_test::files().size();
#else
  size_t n=0;for(int fd=0;fd<4096;++fd)if(::fcntl(fd,F_GETFD)>=0)++n;return n;
#endif
}
Value record(std::vector<Value> values){auto d=Data::make(Data::Record);d->text="OwnedNode";d->values=std::move(values);return Value(std::move(d));}
struct Fixture {
  std::filesystem::path root;
  Fixture(){auto path=(std::filesystem::temp_directory_path()/"nex-cell-owned-XXXXXX").string();require(::mkdtemp(path.data()),"owned-cell fixture directory failed");root=path;std::ofstream(root/"input")<<"abcdef";}
  ~Fixture(){std::error_code error;std::filesystem::remove_all(root,error);}
};
struct Payload {
  unsigned *destroyed;
  std::function<void()> callback;
  Payload(unsigned &destroyed,std::function<void()> callback):destroyed(&destroyed),callback(std::move(callback)){}
  ~Payload()noexcept{++*destroyed;if(callback)callback();}
};
ResourceByteBudget &budget(){static ResourceByteBudget value(8);return value;}
Value owned(const ResourceDomain &domain,unsigned &destroyed,std::function<void()> callback={}){
  static const ExternalResourceType<Payload> type("test::CellOwner",std::string(64,'a'));
  auto resource=ExternalResource::make(domain,type,std::span<const ResourceByteBudget>(&budget(),1),8,std::make_shared<int>(1),[&](const ResourcePermit &permit){permit.check();return std::make_unique<Payload>(destroyed,std::move(callback));});
  return Value(externalValue(std::move(resource)));
}
}
unsigned testManagedCellResources(){
  const auto baseline=liveObjects.load();const auto beforeFiles=descriptors();unsigned cases=0;
  {
    CellHeap heap;
    rejects("E_CELL_VALUE",[&]{heap.create(Value(diagnosticFile(1)));});
    rejects("E_CELL_VALUE",[&]{heap.create(Value(fileValue(FileResource{})));});
  }++cases;
  {
    Fixture fixture;TextFiles files(fixture.root.string(),false);CellHeap heap;
    auto cell=heap.create(Value(fileValue(files.open("input",FileMode::Read))));auto snapshot=heap.read(cell);
    heap.write(cell,Value(fileValue(files.open("input",FileMode::Read))));heap.collect();
    require(fileResource(snapshot.object).read(2).view().size()==2,"owned snapshot lost its file");
    require(fileResource(heap.read(cell).object).read(1).view().size()==1,"file replacement reused old cursor");
    heap.close();require(fileResource(snapshot.object).isOpen(),"heap close closed an independent rooted snapshot");
    require(fileResource(snapshot.object).close(),"snapshot explicit close failed");
  }++cases;
  {
    Fixture fixture;TextFiles files(fixture.root.string(),false);CellHeap heap;const auto opened=descriptors();
    auto cell=heap.create(Value(int64_t(0)));auto file=Value(fileValue(files.open("input",FileMode::Read)));WeakValueOwner<Data> weak=file.object;
    heap.write(cell,record({cell,file}));file={};cell={};heap.collect();
    require(weak.expired()&&descriptors()==opened&&heap.stats().nodes==0,"file-bearing cycle retained its descriptor");
  }++cases;
  {
    ResourceDomain domain;CellHeap heap;unsigned destroyed=0;auto value=owned(domain,destroyed);
    auto cell=heap.create(value);auto snapshot=heap.read(cell);value={};cell={};heap.collect();
    require(destroyed==0&&externalResource(snapshot.object).isOpen(),"rooted external snapshot collected");
    heap.close();require(externalResource(snapshot.object).isOpen(),"heap close renewed or revoked independent authority");
    snapshot={};require(destroyed==1,"last external snapshot did not release actual payload");
  }++cases;
  {
    ResourceDomain domain(1);CellHeap heap;unsigned destroyed=0;
    for(unsigned i=0;i<80;++i){auto cell=heap.create(Value(int64_t(0)));heap.write(cell,record({cell,owned(domain,destroyed)}));cell={};heap.collect();require(destroyed==i+1,"cyclic external owner did not retire before next admission");}
    require(heap.stats().nodes==0,"external cycles left registry nodes");
  }++cases;
  {
    ResourceDomain domain;CellHeap heap;unsigned destroyed=0,denied=0;bool failed=false;auto anchor=heap.create(Value(int64_t(42)));
    auto callback=[&]{
      auto check=[&](auto action){try{action();failed=true;}catch(const DataError &error){if(error.code=="E_CELL_REENTRY")++denied;else failed=true;}catch(...){failed=true;}};
      check([&]{heap.create(Value(int64_t(1)));});check([&]{heap.collect();});check([&]{heap.read(anchor);});
      check([&]{heap.write(anchor,Value(int64_t(0)));});check([&]{heap.stats();});
    };
    {auto discarded=heap.create(owned(domain,destroyed,callback));}
    heap.collect();require(destroyed==1&&denied==5&&!failed&&heap.read(anchor).scalar==42,"resource destructor reentered collection");
  }++cases;
  {
    ResourceDomain domain;auto heap=std::make_unique<CellHeap>();unsigned destroyed=0;
    {auto discarded=heap->create(owned(domain,destroyed,[&]{heap.reset();}));}
    auto entry=heap.get();rejects("E_CELL_CLOSED",[&]{entry->collect();});
    require(!heap&&destroyed==1,"callback-ended heap lost its pinned state");
  }++cases;
  {
    ResourceDomain domain;CellHeap heap({4,3,8});unsigned destroyed=0;auto anchor=heap.create(Value(int64_t(42)));
    {auto discarded=heap.create(owned(domain,destroyed,[&]{heap.close();}));}
    rejects("E_CELL_CLOSED",[&]{heap.create(Value(int64_t(9)));});
    require(destroyed==1&&heap.stats().nodes==0&&anchor.object->values.empty(),"automatic collection published into a closed heap");
  }++cases;
  {
    ResourceDomain domain;CellHeap heap({2,2,8});unsigned destroyed=0;auto cell=heap.create(Value(int64_t(42)));
    auto value=record({owned(domain,destroyed),Value(string("too large"))});
    rejects("E_CELL_LIMIT",[&]{heap.write(cell,value);});
    require(heap.read(cell).scalar==42&&destroyed==0,"failed adoption changed old value or caller ownership");
    value={};require(destroyed==1,"failed adoption retained incoming external owner");
  }++cases;
  {
    ResourceDomain domain;CellHeap heap;unsigned destroyed=0;auto value=owned(domain,destroyed);auto cell=heap.create(value);
    domain.revoke();require(destroyed==1&&!externalResource(heap.read(cell).object).isOpen(),"cell extended revoked resource authority");
    auto closed=heap.create(value);require(equal(heap.read(closed),value),"closed genuine owner cannot be retained as a value");
  }++cases;
  {
    ResourceDomain domain;CellHeap heap;unsigned destroyed=0,denied=0;
    auto cell=heap.create(owned(domain,destroyed,[&]{heap.close();try{heap.stats();}catch(const DataError &error){if(error.code=="E_CELL_REENTRY")++denied;}}));
    heap.close();require(destroyed==1&&denied==1&&heap.stats().nodes==0,"close cleanup reentered a partially retired registry");
  }++cases;
  require(liveObjects.load()==baseline&&descriptors()==beforeFiles&&budget().used()==0,"owned-cell kernel leaked values, files or external capacity");
  return cases;
}
