#include "nex_cells.h"
#include "nex_parallel_value.h"
#include <algorithm>
#include <atomic>
#include <iostream>
#include <stdexcept>
#include <thread>

using namespace nexrt;
static void require(bool condition,const char *message){if(!condition)throw std::runtime_error(message);}
template<class F>static void rejects(const char *code,F action){
  try{action();}catch(const DataError &error){require(error.code==code,"wrong managed heap error");return;}
  throw std::runtime_error("expected a managed heap error");
}
static Value record(std::vector<Value> fields){
  auto data=Data::make(Data::Record);data->text="Node";data->values=std::move(fields);
  for(size_t i=0;i<data->values.size();++i)data->names.push_back("field"+std::to_string(i));
  return Value(data);
}
static Value list(std::vector<Value> values){auto data=Data::make(Data::List);data->values=std::move(values);return Value(data);}

int main(){try{
  const auto baseline=liveObjects.load();unsigned cases=0;
  {
    for(auto kind:{Data::Cell,Data::File,Data::External,Data::Bytes,Data::TaskScope,Data::Task,Data::Channel}){
      rejects("E_RUNTIME",[&]{(void)nexrt::makeValueOwner<Data>(kind);});
      rejects("E_RUNTIME",[&]{(void)Data::make(kind);});
    }
    require(liveObjects.load()==baseline,"rejected constructor changed live-value accounting");++cases;
  }
  {
    CellHeap heap;
    auto first=heap.create(Value(int64_t(1))),alias=first,other=heap.create(Value(int64_t(1)));
    require(equal(first,alias)&&!equal(first,other),"cells use structural equality");
    heap.write(alias,Value(int64_t(2)));require(heap.read(first).scalar==2&&heap.read(other).scalar==1,"alias write was not observed");
    require(printable(first)=="<cell>"&&representation(first)=="\"<cell>\"","cell rendering exposed or traversed its payload");
    const auto before=heap.stats();heap.collect();require(heap.stats().cells==before.cells,"live aliased cells reclaimed");++cases;
  }
  require(liveObjects.load()==baseline,"scalar heap leaked");
  {
    CellHeap heap;auto cell=heap.create(record({Value(int64_t(1))}));auto before=heap.read(cell);
    heap.write(cell,record({Value(int64_t(2))}));require(before.object->values[0].scalar==1,"mutation changed an immutable snapshot");
    require(heap.read(cell).object->values[0].scalar==2,"record write missing");heap.collect();
    require(before.object->values[0].scalar==1,"GC mutated a rooted snapshot");
    heap.close();require(before.object->values[0].scalar==1,"heap close mutated a rooted immutable snapshot");
    rejects("E_CELL_CLOSED",[&]{heap.read(cell);});heap.close();++cases;
  }
  require(liveObjects.load()==baseline,"snapshot heap leaked");
  {
    CellHeap heap;auto self=heap.create(Value(int64_t(0)));nexrt::WeakValueOwner<Data> dead=self.object;
    heap.write(self,self);self=Value();auto result=heap.collect();
    require(result.reclaimedCells==1&&dead.expired()&&heap.stats().nodes==0,"self-cycle was not reclaimed");++cases;
  }
  {
    CellHeap heap;auto left=heap.create(Value(int64_t(0))),right=heap.create(Value(int64_t(0)));
    nexrt::WeakValueOwner<Data> a=left.object,b=right.object;
    heap.write(left,record({right}));heap.write(right,list({left,left}));
    auto alias=left;left=Value();right=Value();heap.collect();
    require(!a.expired()&&!b.expired(),"reachable cyclic graph reclaimed");
    alias=Value();auto result=heap.collect();require(result.reclaimedCells==2&&a.expired()&&b.expired(),"record/list cycle leaked");++cases;
  }
  {
    CellHeap heap;auto cell=heap.create(Value(int64_t(0)));auto closure=Data::make(Data::Closure);
    closure->values={cell};heap.write(cell,Value(closure));nexrt::WeakValueOwner<Data> weak=closure;
    cell=Value();heap.collect();require(!weak.expired(),"external callable root lost");
    closure.reset();heap.collect();require(weak.expired()&&heap.stats().cells==0,"callable capture cycle leaked");++cases;
  }
  {
    CellHeap heap;auto cell=heap.create(Value(int64_t(0)));auto payload=record({cell});heap.write(cell,payload);
    cell=Value();heap.collect();require(heap.stats().cells==1,"immutable snapshot root not traced");
    payload=Value();heap.collect();require(heap.stats().nodes==0,"snapshot-to-cell cycle leaked");++cases;
  }
  require(liveObjects.load()==baseline,"cyclic heap leaked");
  {
    CellHeap heap;auto cell=heap.create(Value(int64_t(0)));heap.write(cell,cell);
    auto outside=list({cell});cell=Value();heap.collect();
    require(heap.stats().cells==1,"an external unregistered container root was lost");
    outside=Value();heap.collect();require(heap.stats().nodes==0,"external container released but cycle retained");++cases;
  }
  {
    // An independent object-ID graph predicts reachability while immutable
    // payload snapshots outlive writes and registry compaction repeats.
    CellHeap heap;constexpr size_t count=96;
    std::vector<Value> roots;std::vector<nexrt::WeakValueOwner<Data>> observed;
    std::vector<std::vector<size_t>> links(count);
    for(size_t i=0;i<count;++i){roots.push_back(heap.create(Value(int64_t(i))));observed.push_back(roots.back().object);}
    for(size_t i=0;i<count;++i){links[i]={i,(i/12)*12+(i+1)%12};heap.write(roots[i],list({roots[links[i][0]],roots[links[i][1]]}));}
    const std::vector<size_t> kept={0,13,26,39};
    for(size_t i=0;i<count;++i)if(std::find(kept.begin(),kept.end(),i)==kept.end())roots[i]=Value();
    std::vector<Value> snapshots(4);std::vector<std::vector<size_t>> snapshotLinks(4);
    auto verify=[&]{
      heap.collect();std::vector<bool> reachable(count,false);std::vector<size_t> work=kept;
      for(const auto &snapshot:snapshotLinks)work.insert(work.end(),snapshot.begin(),snapshot.end());
      while(!work.empty()){auto id=work.back();work.pop_back();if(reachable[id])continue;reachable[id]=true;work.insert(work.end(),links[id].begin(),links[id].end());}
      size_t live=0;for(size_t i=0;i<count;++i){require(observed[i].expired()!=reachable[i],"managed reachability differs from object-ID oracle");live+=reachable[i];}
      require(heap.stats().cells==live,"managed cell count differs from object-ID oracle");
    };
    verify();
    for(size_t turn=0;turn<80;++turn){
      const auto slot=turn%kept.size(),id=kept[slot],other=kept[(turn/3+1)%kept.size()];
      if(turn%3==0){snapshots[slot]=heap.read(roots[id]);snapshotLinks[slot]=links[id];}
      if(turn%5==0){snapshots[(slot+1)%4]=Value();snapshotLinks[(slot+1)%4].clear();}
      links[id]={id,other,other};heap.write(roots[id],list({roots[id],roots[other],roots[other]}));verify();
    }
    snapshots.clear();roots.clear();heap.collect();require(heap.stats().nodes==0,"oracle graph retained unreachable objects");++cases;
  }
  {
    CellHeap heap;auto cell=heap.create(Value(int64_t(1)));
    rejects("E_PARALLEL_VALUE",[&]{validateParallelValue(cell,[]{});});
    auto nested=record({list({cell})});rejects("E_PARALLEL_VALUE",[&]{validateParallelValue(nested,[]{});});
    rejects("E_RUNTIME",[&]{(void)Data::make(*cell.object);});
    rejects("E_RUNTIME",[&]{(void)nexrt::makeValueOwner<Data>(*cell.object);});
    require(heap.read(cell).scalar==1,"rejected transfer/clone changed cell");++cases;
  }
  {
    CellHeap heap;Value head;
    for(unsigned i=0;i<65536;++i)head=heap.create(record({head}));
    require(heap.stats().cells==65536,"long reference chain construction differs");heap.collect();
    require(heap.stats().cells==65536,"long rooted chain reclaimed");
    head=Value();auto result=heap.collect();require(result.reclaimedCells==65536&&heap.stats().nodes==0,"long chain not reclaimed iteratively");++cases;
  }
  require(liveObjects.load()==baseline,"long reference chain leaked");
  {
    CellHeap heap;Value head;
    for(unsigned i=0;i<32768;++i)head=heap.create(record({head}));
    heap.close();require(heap.stats().cells==0,"close retained registered cells");
    rejects("E_CELL_CLOSED",[&]{heap.read(head);});head=Value();++cases;
  }
  {
    CellHeap heap;Value deep=Value(int64_t(1));for(unsigned i=0;i<65536;++i)deep=list({deep});
    auto cell=heap.create(std::move(deep));heap.close();cell=Value();++cases;
  }
  require(liveObjects.load()==baseline,"deep payload teardown leaked");
  {
    CellHeap heap({2,8,64});auto one=heap.create(Value(int64_t(1))),two=heap.create(Value(int64_t(2)));
    rejects("E_CELL_LIMIT",[&]{heap.create(Value(int64_t(3)));});
    require(heap.read(one).scalar==1&&heap.read(two).scalar==2,"limit failure changed rooted values");
    one=Value();auto three=heap.create(Value(int64_t(3)));require(heap.read(three).scalar==3&&heap.stats().cells==2,"budget did not collect prior garbage");++cases;
  }
  {
    CellHeap heap({8,3,16});auto cell=heap.create(Value(int64_t(42)));auto tooLarge=list({record({Value(int64_t(1))}),list({Value(int64_t(2))}),list({Value(int64_t(3))})});
    rejects("E_CELL_LIMIT",[&]{heap.write(cell,tooLarge);});require(heap.read(cell).scalar==42,"failed write changed payload");++cases;
  }
  {
    CellHeap heap({8,32,4});auto cell=heap.create(list({Value(int64_t(1)),Value(int64_t(2))}));
    auto second=heap.create(Value(int64_t(3)));
    rejects("E_CELL_LIMIT",[&]{heap.create(Value(int64_t(4)));});
    rejects("E_CELL_LIMIT",[&]{heap.write(cell,list({Value(int64_t(5))}));});
    require(heap.read(cell).object->values[0].scalar==1&&heap.stats().edges==4,"edge limit failure changed a payload or budget");
    heap.collect();heap.write(cell,Value(int64_t(6)));heap.collect();
    require(heap.stats().edges==2,"retired immutable edges were not reclaimed");
    auto third=heap.create(Value(int64_t(7)));require(heap.read(second).scalar==3&&heap.read(third).scalar==7,"edge reclamation did not restore capacity");++cases;
  }
  {
    CellHeap first,second;auto cell=first.create(Value(int64_t(7)));
    rejects("E_CELL_HEAP",[&]{second.create(list({cell}));});
    rejects("E_CELL_HEAP",[&]{second.read(cell);});require(first.read(cell).scalar==7,"cross-heap failure changed owner");++cases;
  }
  {
    CellHeap heap;auto cell=heap.create(Value(int64_t(9)));std::atomic<bool> rejected=false;
    std::thread worker([&]{
      rejects("E_CELL_THREAD",[&]{heap.read(cell);});rejects("E_CELL_THREAD",[&]{heap.write(cell,Value(int64_t(10)));});
      rejects("E_CELL_THREAD",[&]{heap.create(Value(int64_t(11)));});rejects("E_CELL_THREAD",[&]{heap.collect();});rejected=true;
    });worker.join();
    require(rejected&&heap.read(cell).scalar==9,"thread-affinity contract failed");++cases;
  }
  {
    CellHeap heap({64,256,1024});for(unsigned i=0;i<1024;++i){auto cell=heap.create(Value(int64_t(i)));}
    require(heap.stats().collections>0&&heap.stats().cells<=64,"automatic collection did not bound discarded cells");heap.collect();require(heap.stats().cells==0,"discarded cells retained");++cases;
  }
  require(liveObjects.load()==baseline,"managed heap left live values");
  std::cout<<"{\"ok\":true,\"cases\":"<<cases<<",\"source_type_enabled\":false,\"live_value_delta\":"<<(liveObjects.load()-baseline)<<"}\n";return 0;
}catch(const std::exception &error){std::cerr<<error.what()<<'\n';return 1;}}
