#include "nex/language.h"
#include "nex_cells.h"
#include <iostream>
#include <map>

using namespace nex;
namespace {
using V=nexrt::Value;
llvm::json::Object stats(const nexrt::CellHeap &heap){
  auto s=heap.stats();return llvm::json::Object{{"cells",int64_t(s.cells)},{"nodes",int64_t(s.nodes)},
    {"edges",int64_t(s.edges)},{"collections",int64_t(s.collections)}};
}
std::string field(const llvm::json::Object &o,const char *name){return o.getString(name).value().str();}
}
int main(int argc,char **argv){try{
  if(argc!=2)throw std::runtime_error("expected managed heap trace JSON");
  auto parsed=llvm::json::parse(readFile(argv[1]));if(!parsed)throw std::runtime_error("invalid trace JSON");
  const auto &document=*parsed->getAsObject();nexrt::CellHeapLimits limits;
  if(auto selected=document.getArray("limits"))limits={size_t((*selected)[0].getAsInteger().value()),size_t((*selected)[1].getAsInteger().value()),size_t((*selected)[2].getAsInteger().value())};
  const auto baseline=nexrt::liveObjects.load();nexrt::CellHeap heap(limits);std::map<std::string,V> values;
  auto resolve=[&](const llvm::json::Value &value)->V{
    if(auto number=value.getAsInteger())return V(*number);
    if(auto boolean=value.getAsBoolean())return V(*boolean,true);
    const auto &o=*value.getAsObject();
    if(auto name=o.getString("ref"))return values.at(name->str());
    if(auto number=o.getNumber("f64"))return V::floating(*number);
    return V(std::stoll(field(o,"i64")));
  };
  const std::map<std::string,nexrt::Data::Kind> kinds={{"string",nexrt::Data::String},{"bytes",nexrt::Data::Bytes},{"list",nexrt::Data::List},{"record",nexrt::Data::Record},{"success",nexrt::Data::Success},{"failure",nexrt::Data::Failure},{"enum",nexrt::Data::Enum},{"closure",nexrt::Data::Closure}};
  llvm::json::Array events;
  for(const auto &command:*document.getArray("commands")){
    const auto &c=*command.getAsObject();auto op=field(c,"op");llvm::json::Object event{{"op",op}};
    try{
      if(op=="node"){
        auto kind=kinds.at(field(c,"kind"));auto data=kind==nexrt::Data::Bytes?nexrt::bytes(nexrt::ByteBuffer::copy({})):nexrt::makeValueOwner<nexrt::Data>(kind);
        if(auto fields=c.getArray("values"))for(const auto &v:*fields)data->values.push_back(resolve(v));
        values[field(c,"id")]=V(std::move(data));
      }else if(op=="literal")values[field(c,"id")]=resolve(*c.get("value"));
      else if(op=="create")values[field(c,"id")]=heap.create(resolve(*c.get("value")));
      else if(op=="alias")values[field(c,"id")]=values.at(field(c,"from"));
      else if(op=="read")values[field(c,"id")]=heap.read(values.at(field(c,"cell")));
      else if(op=="write")heap.write(values.at(field(c,"cell")),resolve(*c.get("value")));
      else if(op=="drop")values.erase(field(c,"id"));
      else if(op=="same"){
        const auto &a=values.at(field(c,"a")),&b=values.at(field(c,"b"));
        event["same"]=a.tag==b.tag&&(a.tag==V::Object?a.object==b.object:a.scalar==b.scalar);
      }else if(op=="collect"){
        auto r=heap.collect();event["collection"]=llvm::json::Object{{"beforeCells",int64_t(r.beforeCells)},{"afterCells",int64_t(r.afterCells)},
          {"reclaimedCells",int64_t(r.reclaimedCells)},{"reclaimedNodes",int64_t(r.reclaimedNodes)}};
      }else if(op=="chain"||op=="deep"){
        V head(int64_t(0));const auto count=c.getInteger("count").value();
        for(int64_t i=0;i<count;++i){auto node=nexrt::makeValueOwner<nexrt::Data>(nexrt::Data::List);node->values.push_back(std::move(head));head=V(std::move(node));if(op=="chain")head=heap.create(std::move(head));}
        if(op=="deep")head=heap.create(std::move(head));
        values[field(c,"id")]=std::move(head);
      }else if(op=="close")heap.close();
      else throw std::runtime_error("unknown trace operation");
    }catch(const nexrt::DataError &error){event["code"]=error.code;}
    event["stats"]=stats(heap);events.push_back(std::move(event));
  }
  values.clear();heap.close();
  if(nexrt::liveObjects.load()!=baseline)throw std::runtime_error("trace left live runtime data");
  std::cout<<json(llvm::json::Object{{"events",std::move(events)},{"final",stats(heap)},{"live_delta",0}},false)<<'\n';return 0;
}catch(const std::exception &error){std::cerr<<error.what()<<'\n';return 1;}}
