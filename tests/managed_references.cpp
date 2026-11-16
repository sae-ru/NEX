#include "nex/managed_references.h"
#include "nex/backend.h"
#include "nex/web.h"
#include <iostream>
#include <stdexcept>

using namespace nex;
namespace {
unsigned accepted=0,rejected=0;
void require(bool value,const std::string &message){if(!value)throw std::runtime_error(message);}
template<class F>void rejects(const std::string &code,F action){
  try{action();}catch(const Error &error){require(error.code==code,"expected "+code+", got "+error.code+": "+error.message);++rejected;return;}
  throw std::runtime_error("expected "+code);
}
Program checked(const std::string &source){auto p=parseManagedReferencesPrototype("module refs;\n"+source,"refs.nex");check(p);return p;}
void runs(const std::string &source,const std::string &output,nexrt::CellHeapLimits limits={}){
  const auto baseline=nexrt::liveObjects.load();
  {
    auto p=checked(source);auto result=evaluateManagedReferencesPrototype(p,"main",2000000,limits);
    require(result.evaluation.output==output,"unexpected private reference output: "+result.evaluation.output);
    require(result.afterCollection.cells==0&&result.afterCollection.nodes==0,"completed source context retained unreachable references");
  }
  require(nexrt::liveObjects.load()==baseline,"private reference execution leaked values");++accepted;
}
void bad(const std::string &source,const std::string &code){rejects(code,[&]{checked(source);});}
}
int main(int argc,char **argv){try{
  require(argc==2,"expected public baseline fixture");const auto baseline=nexrt::liveObjects.load();
  runs(R"nex(
fn make()->cell<i64>!{state}{return cell_new(1);}
fn main()->unit!{state,io}{
 let original:cell<i64>=make();let alias:cell<i64>=original;let other:cell<i64>=make();
 assert(original==alias);assert(original!=other);cell_write(alias,42);
 assert(cell_read(other)==1);print(cell_read(original));print(original);
}
)nex","42\n<cell>\n");
  runs(R"nex(
fn receiver(log:cell<str>,value:cell<i64>)->cell<i64>!{state}{cell_write(log,cell_read(log)+"r");return value;}
fn value(log:cell<str>)->i64!{state}{cell_write(log,cell_read(log)+"v");return 42;}
fn touch(log:cell<str>)->bool!{state}{cell_write(log,"wrong");return true;}
fn main()->unit!{state,io}{
 let log:cell<str>=cell_new("");let target:cell<i64>=cell_new(0);
 cell_write(receiver(log,target),value(log));print(cell_read(log));print(cell_read(target));
 let a:bool=false&&touch(log);let b:bool=true||touch(log);assert(!a&&b);print(cell_read(log));
}
)nex","rv\n42\nrv\n");
  runs(R"nex(
fn counter()->fn()->i64!{state}!{state}{
 let stored:cell<i64>=cell_new(0);var snapshot:i64=2;
 let next:fn()->i64!{state}=fn()->i64!{state}{cell_write(stored,cell_read(stored)+1);return cell_read(stored)+snapshot;};
 snapshot=100;return next;
}
fn main()->unit!{state,io}{let next:fn()->i64!{state}=counter();print(next());cell_collect();print(next());}
)nex","3\n4\n");
  runs(R"nex(
struct Box<T>{value:T;}
fn replace<T>(target:cell<T>,value:T)->T!{state}{let old:T=cell_read(target);cell_write(target,value);return old;}
fn identity<F<_>,T>(value:F<T>)->F<T>{return value;}
fn apply<T>(value:fn()->T!{?e})->T!{?e}{return value();}
fn main()->unit!{state,io}{
 let stored:cell<Box<list<i64>>>=cell_new(Box([1,2]));let same:cell<Box<list<i64>>>=identity(stored);
 let old:Box<list<i64>>=replace(same,Box([3]));let explicit:cell<Box<list<i64>>>=identity<cell,Box<list<i64>>>(stored);
 assert(explicit==stored);cell_collect();print(old.value);print(cell_read(stored).value);
 let empty:cell<list<i64>>=cell_new<list<i64>>([]);cell_write(empty,[42]);
 print(apply(fn()->i64!{state}{return cell_read(empty)[0];}));
}
)nex","[1,2]\n[3]\n42\n");
  runs(R"nex(
struct Node{value:i64;next:list<cell<Node>>;}
enum Link{None;Some(value:cell<Node>);}
fn main()->unit!{state,io}{
 let left:cell<Node>=cell_new(Node(1,[]));let right:cell<Node>=cell_new(Node(2,[left]));
 cell_write(left,Node(3,[left,right,right]));let old:Node=cell_read(left);
 cell_write(left,Node(4,[]));cell_collect();assert(old.value==3&&old.next[0]==left&&old.next[1]==right);
 let link:Link=Link::Some(left);match link{Link::None()=>{assert(false);}Link::Some(alias)=>{assert(alias==left);}}
 print(old.value);print(cell_read(left).value);
}
)nex","3\n4\n");
  runs(R"nex(
fn main()->unit!{state,io}{
 let slot:cell<fn()->i64>=cell_new(fn()->i64{return 0;});
 cell_write(slot,fn()->i64{assert(slot==slot);return 42;});cell_collect();print(cell_read(slot)());
}
)nex","42\n");
  runs(R"nex(
fn raise(value:cell<i64>)->unit!{throw}{throw(value);}
fn returned(value:cell<i64>)->cell<i64>!{state}{try{return value;}finally{cell_write(value,50);}}
fn failed(value:cell<i64>)->result<i64>!{state}{
 try{let absent:i64=err<i64>("missing","missing")?;return ok(absent);}finally{cell_write(value,99);}
}
fn main()->unit!{state,io,throw}{
 let stored:cell<i64>=cell_new(42);
 try{raise(stored);}catch(alias:cell<i64>){assert(alias==stored);cell_collect();cell_write(alias,43);}
 finally{cell_write(stored,cell_read(stored)+1);}
 print(cell_read(stored));assert(returned(stored)==stored);print(cell_read(stored));
 assert(!is_ok(failed(stored)));print(cell_read(stored));
}
)nex","44\n50\n99\n");
  runs(R"nex(
struct Node{next:list<cell<Node>>;}
fn main()->unit!{state,io}{var i:i64=0;while i<1024{
 let cycle:cell<Node>=cell_new(Node([]));cell_write(cycle,Node([cycle]));i=i+1;
}cell_collect();print(i);}
)nex","1024\n",{32,256,512});
  runs(R"nex(
struct Node{value:i64;next:list<cell<Node>>;}
fn main()->unit!{state,io}{var head:list<cell<Node>>=[];var i:i64=0;
 while i<2048{head=[cell_new(Node(i,head))];i=i+1;}cell_collect();print(cell_read(head[0]).value);
}
)nex","2047\n");
  runs(R"nex(

struct Pair<A,B>{first:A;second:B;}
struct Wrapped<F<_>,T>{value:F<T>;}
fn forward<F<_>,T>(value:F<T>)->F<T>{return value;}
fn forward2<F<_,_>,A,B>(value:F<A,B>)->F<A,B>{return value;}
fn hold<F<_>,T>(value:F<T>)->Wrapped<F,T>{return Wrapped<F,T>(value);}
fn main()->unit!{state,io}{
 let anchor:cell<i64>=cell_new(1);
 let pair:Pair<cell<i64>,str>=forward<Pair<cell<i64>,_>,str>(Pair(anchor,"old"));
 let inferred:Pair<cell<i64>,str>=forward(pair);
 let leading:Pair<cell<i64>,str>=forward<Pair<_,str>,cell<i64>>(pair);
 let multi:Pair<cell<i64>,str>=forward2<Pair<_,_>,cell<i64>,str>(pair);
 let held:Wrapped<Pair<cell<i64>,_>,str>=hold<Pair<cell<i64>,_>,str>(pair);
 let stored:cell<Pair<cell<i64>,str>>=cell_new(held.value);
 let old:Pair<cell<i64>,str>=cell_read(stored);
 cell_write(stored,Pair(anchor,"new"));cell_write(anchor,42);cell_collect();
 assert(old.second=="old");assert(cell_read(stored).second=="new");
 assert(inferred.first==anchor&&leading.first==anchor&&multi.first==anchor);
 print(cell_read(old.first));print(old.second);print(cell_read(stored).second);
}
)nex","42\nold\nnew\n");
  runs(R"nex(

struct Wrap<F<_>>{value:F<i64>;}
struct H<F<_<_>>,G<_>>{value:F<G>;}
fn hold<F<_<_>>,G<_>>(value:F<G>)->F<G>{return value;}
fn main()->unit!{state,io}{
 let anchor:cell<i64>=cell_new(1);
 let wrap:Wrap<cell>=Wrap<cell>(anchor);
 let held:Wrap<cell>=hold<Wrap,cell>(wrap);
 let nested:H<Wrap,cell>=H<Wrap,cell>(held);
 let slot:cell<H<Wrap,cell>>=cell_new(nested);
 let reader:fn()->i64!{state}=fn()->i64!{state}{cell_collect();return cell_read(cell_read(slot).value.value);};
 cell_write(anchor,42);cell_collect();print(reader());
 assert(cell_read(slot).value.value==anchor);
}
)nex","42\n");
  runs(R"nex(

trait Content{type Item;fn get(value:Self)->Content::Item<Self>!{state};}
fn extract<T>(value:cell<T>)->T!{state}{return cell_read(value);}
impl cells<T>:Content for cell<T>{type Item=T;get=extract<T>;}
fn read<T:Content>(value:T)->Content::Item<T>!{state}{return Content<T>::get(value);}
fn main()->unit!{state,io}{
 let anchor:cell<str>=cell_new("old");
 let getter:fn(cell<str>)->str!{state}=Content<cell<str>>::get;
 let slot:cell<fn(cell<str>)->str!{state}>=cell_new(getter);
 cell_write(anchor,"Я🌍");cell_collect();print(read(anchor));print(cell_read(slot)(anchor));
}
)nex","Я🌍\nЯ🌍\n");
  runs(R"nex(

struct Pair<A,B>{first:A;second:B;}
fn raise<F<_>,T>(value:F<T>)->unit!{throw}{match true{true=>{let alias:F<T>=value;throw(alias);}false=>{throw(value);}}}
fn apply<T>(callback:fn()->T!{?e})->T!{?e}{return callback();}
fn relay(value:cell<i64>)->unit!{state,throw}{
 try{apply(fn()->i64!{throw}{raise<Pair<cell<i64>,_>,str>(Pair(value,"caught"));return 0;});}
 finally{cell_collect();cell_write(value,42);}
}
fn main()->unit!{state,io,throw}{
 let anchor:cell<i64>=cell_new(0);
 try{relay(anchor);}catch(packet:Pair<cell<i64>,str>){cell_collect();assert(packet.first==anchor);print(packet.second);print(cell_read(packet.first));}
}
)nex","caught\n42\n");
  runs(R"nex(
trait Mapper<Self<_>>{fn map<A,B>(value:Self<A>,apply:fn(A)->B)->Self<B>!{state};}
fn map_cell<A,B>(value:cell<A>,apply:fn(A)->B)->cell<B>!{state}{return cell_new(apply(cell_read(value)));}
impl cell_mapper:Mapper for cell{map=map_cell;}
fn convert<F<_>:Mapper,A,B>(value:F<A>,apply:fn(A)->B)->F<B>!{state}{return Mapper<F>::map<A,B>(value,apply);}
fn main()->unit!{state,io}{
 let anchor:cell<i64>=cell_new(41);
 let mapped:cell<str>=convert<cell,i64,str>(anchor,fn(value:i64)->str{return str(value+1);});
 let direct:cell<i64>=Mapper<cell>::map<i64,i64>(anchor,fn(value:i64)->i64{return value+2;});
 cell_write(anchor,0);cell_collect();print(cell_read(mapped));print(cell_read(direct));print(cell_read(anchor));
}
)nex","42\n43\n0\n");
  runs(R"nex(
struct Box<T=i64>{value:T;}
fn keep<T>(value:T)->T requires(value==value) ensures(result=>result==value){return value;}
fn make<T=i64>(value:T)->Box<T>{return Box<T>(value);}
fn main()->unit!{state,io}{let anchor:cell<i64>=cell_new(41);let same:cell<i64>=keep(anchor);let wrapped:Box<cell<i64>>=make(same);cell_write(anchor,42);cell_collect();print(cell_read(wrapped.value));let simple:Box=make(7);print(simple.value);}
)nex","42\n7\n");
  {
    auto scalar=checked("fn main()->i64!{state}{let x:cell<i64>=cell_new(42);return cell_read(x);}");
    auto value=evaluateManagedReferencesPrototype(scalar);require(value.evaluation.value.getAsInteger()==42&&value.afterCollection.nodes==0,"host scalar result retained its source cell");++accepted;
    auto snapshot=checked("fn main()->list<i64>!{state}{let x:cell<list<i64>>=cell_new([1,2]);let old:list<i64>=cell_read(x);cell_write(x,[3]);return old;}");
    auto immutable=evaluateManagedReferencesPrototype(snapshot);require(json(immutable.evaluation.value,false)=="[1,2]"&&immutable.afterCollection.nodes==0,"host immutable snapshot result changed or retained runtime nodes");++accepted;
  }
  for(const auto &[source,code]:std::vector<std::pair<std::string,std::string>>{
    {"fn main()->unit{cell_new(1);}","E_EFFECT"},
    {"fn read(x:cell<i64>)->i64{return cell_read(x);}fn main()->unit{}","E_EFFECT"},
    {"fn write(x:cell<i64>)->unit{cell_write(x,1);}fn main()->unit{}","E_EFFECT"},
    {"fn main()->unit{cell_collect();}","E_EFFECT"},
    {"fn mutate()->unit!{state}{}fn main()->unit{mutate();}","E_EFFECT"},
    {"fn read(x:cell<i64>)->i64!{state}requires(cell_read(x)>0){return 1;}fn main()->unit{}","E_EFFECT"},
    {"fn main()->unit!{state}{let x:cell<i64>=cell_new(1);cell_write(x,\"bad\");}","E_TYPE"},
    {"fn main()->unit!{state}{cell_new<i64>(true);}","E_TYPE"},
    {"fn nothing()->unit{}fn main()->unit!{state}{cell_new(nothing());}","E_TYPE"},
    {"fn main()->unit!{state}{cell_read(1);}","E_CELL_TYPE"},
    {"fn main()->unit!{state}{cell_new();}","E_ARITY"},
    {"fn main()->unit!{state}{let x:cell<i64>=cell_new(1);cell_read<i64>(x);}","E_GENERIC_ARITY"},
    {"fn main()->unit!{state}{cell_new<i64,str>(1);}","E_GENERIC_ARITY"},
    {"server fn read(x:file)->cell<file>!{state}{return cell_new(x);}fn main()->unit{}","E_CELL_VALUE"},
    {"server resource Owner;server fn hold(value:Owner)->cell<Owner>!{state}{return cell_new(value);}","E_CELL_VALUE"},
    {"server resource Owner;struct Box<T>{value:T;}server fn hold(value:Box<Owner>)->cell<Box<Owner>>!{state}{return cell_new(value);}","E_CELL_VALUE"},
    {"server extern fn read(value:cell<i64>)->i64!{ffi}=foreign(\"host\",\"read\",\"0000000000000000000000000000000000000000000000000000000000000000\");","E_FFI_SIGNATURE"},
    {"fn main()->unit!{state}{let x:cell<i64>=cell_new(1);encode_json(x);}","E_GENERIC_BOUND"},
    {"struct Marker<T>{}fn wire(x:Marker<cell<i64>>)->str{return encode_json(x);}fn main()->unit{}","E_GENERIC_BOUND"},
    {"struct Wrap<F<_>>{value:F<i64>;}struct Marker<F<_<_>>,G<_>>{}fn main()->unit{let marker:Marker<Wrap,cell>=Marker<Wrap,cell>();encode_json(marker);}","E_GENERIC_BOUND"},
    {"trait Content{type Item;fn get(value:Self)->Content::Item<Self>!{state};}fn extract<T>(value:cell<T>)->T!{state}{return cell_read(value);}impl cells<T>:Content for cell<T>{type Item=T;get=extract<T>;}fn read<T:Content>(value:T)->Content::Item<T>{return Content<T>::get(value);}fn main()->unit{}","E_EFFECT"},
    {"struct Wrap<F<_>>{value:F<i64>;}fn hold<F<_<_>>,G<_>>(value:F<G>)->F<G>{return value;}fn main()->unit!{state}{let stored:cell<i64>=cell_new(1);hold<cell,cell>(stored);}","E_GENERIC_KIND"},
    {"fn main()->unit{parallel_map([1],fn(x:i64)->i64{return x;},1);}","E_CELL_STAGE"},
    {"server fn main()->unit!{db}{}","E_CELL_STAGE"},
    {"import \"other.nex\" as other;fn main()->unit{}","E_CELL_STAGE"}
  })bad(source,code);
  auto p=checked("fn main()->unit!{state}{let x:cell<i64>=cell_new(1);cell_write(x,2);}");
  rejects("E_CELL_MIGRATION",[&]{revision(p);});rejects("E_CELL_MIGRATION",[&]{sourceBundle(p);});rejects("E_CELL_MIGRATION",[&]{dependencyLock(p);});
  rejects("E_CELL_BACKEND",[&]{evaluate(p,"main");});rejects("E_CELL_BACKEND",[&]{emitMLIR(p);});
  rejects("E_CELL_BACKEND",[&]{emitWasmMLIR(p,"main",false);});rejects("E_CELL_BACKEND",[&]{emitTypeScript(p,{{"main","main"}});});
  rejects("E_LANGUAGE_VERSION",[&]{parseVersioned("module empty;fn main()->unit{}","empty.nex",SourceLanguage::ManagedReferencesPrototype);});
  p.functions[0].checked=false;rejects("E_CELL_STATE",[&]{evaluateManagedReferencesPrototype(p);});
  auto resultCell=checked("fn main()->cell<i64>!{state}{return cell_new(1);}");
  rejects("E_CELL_ENTRY",[&]{evaluateManagedReferencesPrototype(resultCell);});
  auto overflow=checked("fn main()->unit!{state}{let x:cell<i64>=cell_new(1);cell_write(x,9223372036854775807+1);}");
  rejects("E_OVERFLOW",[&]{evaluateManagedReferencesPrototype(overflow);});
  auto uncaught=checked("fn main()->unit!{state,throw}{let x:cell<i64>=cell_new(1);throw(x);}");
  rejects("E_SOURCE_EXCEPTION",[&]{evaluateManagedReferencesPrototype(uncaught);});
  auto exhausted=checked("fn main()->unit!{state}{let a:cell<i64>=cell_new(1);let b:cell<i64>=cell_new(2);let c:cell<i64>=cell_new(3);}");
  rejects("E_CELL_LIMIT",[&]{evaluateManagedReferencesPrototype(exhausted,"main",1000,{2,8,16});});
  auto fixture=llvm::json::parse(readFile(argv[1]));require(bool(fixture),"invalid public baseline fixture");auto object=fixture->getAsObject();
  const auto source=object->getString("source")->str();
  for(const auto &row:*object->getArray("cases")){
    const auto language=row.getAsObject()->getString("language")->str();
    auto publicProgram=loadVersionedBundle(llvm::json::Object{{"schema","nex.sources/1"},{"entry","main.nex"},{"files",llvm::json::Object{{"main.nex",source}}}},".",language);
    require(revision(publicProgram)==row.getAsObject()->getString("revision")->str(),"private reference work changed an archived public revision");
    require(evaluate(publicProgram,"public_cells::main").value.getAsInteger()==42,"private reference constructor changed a user cell<T> type");
    require(!supportsManagedReferences(publicProgram),"public source acquired reference semantics");
    rejects("E_LANGUAGE_VERSION",[&]{evaluateManagedReferencesPrototype(publicProgram);});++accepted;
  }
  for(auto language:{SourceLanguage::Contracts028,SourceLanguage::Contracts029}){
    rejects("E_EFFECT",[&]{auto old=parseVersioned("module old;fn main()->unit!{state}{}","old.nex",language);check(old);});
    rejects("E_GENERIC_ARITY",[&]{auto old=parseVersioned("module old;fn f(x:cell<i64>)->unit{}fn main()->unit{}","old.nex",language);check(old);});
  }
  {
    auto modules=loadManagedReferencesPrototypeBundle(llvm::json::Object{
      {"schema","nex.private-reference-sources/1"},{"entry","main.nex"},{"files",llvm::json::Object{
        {"main.nex","module app;import \"./value.nex\" as value;fn main()->unit!{state,io}{let target:cell<i64>=value::make();value::change(target);cell_collect();print(cell_read(target));}"},
        {"value.nex","module value;pub fn make()->cell<i64>!{state}{return cell_new(1);}pub fn change(target:cell<i64>)->unit!{state}{cell_write(target,42);}"}}}},".");
    auto result=evaluateManagedReferencesPrototype(modules);
    require(modules.units.size()==2&&result.evaluation.output=="42\n"&&result.afterCollection.nodes==0,"private module calls lost shared cell state or roots");++accepted;
  }
  require(nexrt::liveObjects.load()==baseline,"private reference error or source packet leaked values");
  std::cout<<"{\"ok\":true,\"accepted_scenarios\":"<<accepted<<",\"rejected_scenarios\":"<<rejected<<",\"public_source_enabled\":false,\"live_value_delta\":"<<(nexrt::liveObjects.load()-baseline)<<"}\n";
  return 0;
}catch(const Error &error){std::cerr<<error.code<<": "<<error.message<<" at "<<error.span.line<<":"<<error.span.column<<" after "<<accepted<<" accepted / "<<rejected<<" rejected scenarios\n";return 1;}
catch(const std::exception &error){std::cerr<<error.what()<<'\n';return 1;}}
