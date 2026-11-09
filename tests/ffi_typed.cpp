#include "host_test.h"
#include "nex_ffi_host.h"
#include "nex_files.h"
#include "nex_host.h"
#include "nex_json.h"
#include "third_party/json.hpp"
#include <filesystem>
#include <fstream>
#include <iostream>
#include <thread>
#include <atomic>
#include <fcntl.h>
#include <unistd.h>
using namespace nexrt;using J=nlohmann::ordered_json;
extern "C" nex_ffi_status nex_example_c_nominal(const nex_ffi_api_v1*,nex_ffi_call,const nex_ffi_ref*,uint64_t,nex_ffi_ref*,void*);
namespace {
const auto *api=nex_ffi_get_api(1,sizeof(nex_ffi_api_v1));
void require(bool condition,const char *message){if(!condition)throw std::runtime_error(message);}
void ok(nex_ffi_status status){require(!status,"C API status failed");}
template<class F> void error(const char *code,F body){try{body();}catch(const DataError &e){if(e.code!=code)throw std::runtime_error(std::string("expected ")+code+", got "+e.code+": "+e.what());return;}throw std::runtime_error("missing expected error");}
using Body=std::function<nex_ffi_status(nex_ffi_call,const nex_ffi_ref*,uint64_t,nex_ffi_ref*)>;
Value typed(Body body,const ForeignSignature &signature,std::vector<Value> args={},std::function<void()> poll={},ForeignCallLimits limits={}){
 auto bridge=[](const nex_ffi_api_v1*,nex_ffi_call c,const nex_ffi_ref *a,uint64_t n,nex_ffi_ref *o,void *p)->nex_ffi_status{return (*static_cast<Body*>(p))(c,a,n,o);};return invokeForeignTyped(bridge,args,signature,&body,std::move(poll),limits);
}
ForeignSignature signature(J types,J parameters,int result){return ForeignSignature(J{{"schema","nex.foreign-signature/1"},{"parameters",parameters},{"result",result},{"types",types}}.dump());}
J primitive(const char *kind){return J{{"kind",kind}};}
J field(const char *name,int type){return J{{"name",name},{"type",type}};}
J record(const char *name,J fields){return J{{"kind","record"},{"name",name},{"fields",fields}};}
J variant(const char *name,J fields){return J{{"name",name},{"fields",fields}};}
J enumeration(const char *name,J variants){return J{{"kind","enum"},{"name",name},{"variants",variants}};}
ForeignSignature integer(){return signature(J::array({primitive("i64")}),J::array({0}),0);}
auto echo=[](auto,auto a,auto,auto o)->nex_ffi_status{*o=a[0];return NEX_FFI_OK;};
int descriptors(){
#ifdef _WIN32
return int(nex_test::files().size());
#else
int count=0;for(int fd=0;fd<1024;++fd)if(::fcntl(fd,F_GETFD)>=0)++count;return count;
#endif
}
struct Directory {
 std::filesystem::path root;
 Directory(){auto p=(std::filesystem::temp_directory_path()/"nex-ffi-types-XXXXXX").string();require(::mkdtemp(p.data()),"mkdtemp failed");root=p;std::ofstream(root/"input")<<"data";}
 ~Directory(){std::error_code e;std::filesystem::remove_all(root,e);}
};
std::string read(const char *path){std::ifstream in(path);if(!in)throw std::runtime_error("cannot read signature");return {std::istreambuf_iterator<char>(in),{}};}
}
int main(int argc,char **argv){try{
 if(argc==3&&std::string(argv[1])=="--signature"){
  ForeignSignature contract(read(argv[2]));std::vector<uint8_t> data{0,255,128,1};std::vector<Value> args{Value(bytes(ByteBuffer::copy(data)))};
  std::cout<<encodeJSON(invokeForeignTyped(nex_example_c_nominal,args,contract))<<'\n';return 0;
 }
 unsigned count=0;auto run=[&](const char *name,auto body){auto fds=descriptors();body();require(liveObjects==0,"managed value leak");require(descriptors()==fds,"descriptor leak");++count;std::cout<<"PASS "<<name<<std::endl;};
 run("explicit fatal traps precede nominal and unit return validation",[]{
  for(auto s:{signature(J::array({primitive("i64"),record("Box",J::array({field("value",0)}))}),J::array({0}),1),
              signature(J::array({primitive("i64"),primitive("unit")}),J::array({0}),1)}){
   bool trapped=false;
   try{typed([](auto c,auto a,auto,auto o){
    nex_ffi_ref retained=0;const uint8_t bytes[]={0,255,128};
    ok(api->make_bytes(c,bytes,sizeof(bytes),&retained));
    require(api->raise_trap(c,reinterpret_cast<const uint8_t*>("E_ASSERT"),8,reinterpret_cast<const uint8_t*>("typed fatal: Я"),15)==NEX_FFI_HOST_TRAP,"typed trap rejected");
    *o=a[0];return NEX_FFI_OK; // deliberately wrong for either result signature
   },s,{Value(42)});}catch(const DataError &e){trapped=e.code=="E_ASSERT"&&std::string(e.what())=="typed fatal: Я";}
   require(trapped,"return validation or ignored status replaced explicit trap");
  }
 });
 run("scalar signatures reject wrong arguments before entering C",[]{
  auto s=integer();bool entered=false;error("E_FFI_TYPE",[&]{typed([&](auto,auto,auto,auto){entered=true;return NEX_FFI_OK;},s,{Value(1,true)});});require(!entered,"wrong argument entered C");
  error("E_FFI_TYPE",[&]{typed(echo,s,{});});require(typed(echo,s,{Value(42)}).scalar==42,"typed scalar roundtrip differs");
 });
 run("untyped calls expose no signature or nominal construction authority",[]{
  auto bridge=[](const nex_ffi_api_v1 *a,nex_ffi_call c,const nex_ffi_ref*,uint64_t,nex_ffi_ref *o,void*)->nex_ffi_status{nex_ffi_type t=77;uint64_t n=99;require(a->result_type(c,&t)==NEX_FFI_TYPE&&t==77,"untyped call acquired type authority");require(a->signature_size(c,&n)==NEX_FFI_TYPE&&n==99,"untyped signature read succeeded");return a->make_i64(c,42,o);};require(invokeForeign(bridge,{}).scalar==42,"untyped transport changed");
 });
 run("wrong scalar and heterogeneous list results are rejected",[]{
  auto s=signature(J::array({primitive("i64"),J{{"kind","list"},{"item",0}}}),J::array({0}),1);
  error("E_FFI_TYPE",[&]{typed(echo,s,{Value(42)});});
  error("E_FFI_TYPE",[&]{typed([](auto c,auto a,auto,auto o){nex_ffi_ref b=0;ok(api->make_bool(c,1,&b));nex_ffi_ref fields[]={a[0],b};return api->make_list(c,fields,2,o);},s,{Value(42)});});
 });
 run("result payloads are checked through success and failure",[]{
  auto s=signature(J::array({primitive("i64"),J{{"kind","result"},{"item",0}}}),J::array({0}),1);
  auto good=typed([](auto c,auto a,auto,auto o){return api->make_success(c,a[0],o);},s,{Value(42)});require(unwrap(good).scalar==42,"success result differs");
  error("E_FFI_TYPE",[&]{typed([](auto c,auto,auto,auto o){nex_ffi_ref b=0;ok(api->make_bool(c,1,&b));return api->make_success(c,b,o);},s,{Value(42)});});
  auto failure=typed([](auto c,auto,auto,auto o){const uint8_t e[]={'E'},m[]={'x',0,'y'};return api->make_failure(c,e,1,m,3,o);},s,{Value(42)});require(!isSuccess(failure)&&failure.object->values[0].object->text==std::string("x\0y",3),"failure payload changed");
 });
 run("unit is a result without a value token",[]{
  auto s=signature(J::array({primitive("unit")}),J::array(),0);
  typed([](auto c,auto,auto,auto o){nex_ffi_type type=0;uint32_t kind=0;ok(api->result_type(c,&type));ok(api->type_kind(c,type,&kind));require(kind==NEX_FFI_UNIT,"unit type lost");*o=0;return NEX_FFI_OK;},s);
  error("E_FFI_TYPE",[&]{typed([](auto c,auto,auto,auto o){return api->make_i64(c,0,o);},s);});
 });
 run("record constructors use checked identities and ordered field layouts",[]{
  auto s=signature(J::array({primitive("i64"),record("model::Box<i64>",J::array({field("value",0)}))}),J::array({0}),1);
  auto value=typed([](auto c,auto a,auto,auto o){nex_ffi_type type=0;ok(api->result_type(c,&type));return api->make_nominal(c,type,0,a,1,o);},s,{Value(42)});
  require(value.object->text=="model::Box<i64>"&&value.object->names==std::vector<std::string>({"value"})&&value.object->values[0].scalar==42,"nominal constructor layout differs");
 });
 run("wrong nominal fields and constructor arity leave output unchanged",[]{
  auto s=signature(J::array({primitive("i64"),record("Box",J::array({field("value",0)}))}),J::array({0}),1);
  typed([](auto c,auto a,auto,auto o){nex_ffi_type type=0;ok(api->result_type(c,&type));nex_ffi_ref bad=0,out=77;ok(api->make_bool(c,1,&bad));require(api->make_nominal(c,type,0,&bad,1,&out)==NEX_FFI_TYPE&&out==77,"wrong field accepted");require(api->make_nominal(c,type,0,nullptr,0,&out)==NEX_FFI_TYPE&&out==77,"wrong arity accepted");return api->make_nominal(c,type,0,a,1,o);},s,{Value(42)});
 });
 run("different and phantom nominal identities cannot be interchanged",[]{
  auto s=signature(J::array({record("Tag<i64>",J::array()),record("Tag<str>",J::array())}),J::array({0}),1);auto original=std::make_shared<Data>(Data::Record);original->text="Tag<i64>";
  error("E_FFI_TYPE",[&]{typed(echo,s,{Value(original)});});
  auto v=typed([](auto c,auto,auto,auto o){nex_ffi_type type=0;ok(api->result_type(c,&type));return api->make_nominal(c,type,0,nullptr,0,o);},s,{Value(original)});require(v.object->text=="Tag<str>","phantom identity was erased");
 });
 run("nominal labels consume copied-byte quota even without payload fields",[]{
  auto s=signature(J::array({record("LongName",J::array())}),J::array(),0);
  error("E_FFI",[&]{typed([](auto c,auto,auto,auto o){nex_ffi_type t=0;ok(api->result_type(c,&t));nex_ffi_ref out=77;require(api->make_nominal(c,t,0,nullptr,0,&out)==NEX_FFI_LIMIT&&out==77,"nominal label bypassed quota");*o=0;return NEX_FFI_LIMIT;},s,{},{},{4096,7,65536});});
  auto v=typed([](auto c,auto,auto,auto o){nex_ffi_type t=0;ok(api->result_type(c,&t));return api->make_nominal(c,t,0,nullptr,0,o);},s,{},{},{4096,8,65536});require(v.object->text=="LongName","exact nominal label quota failed");
 });
 run("wrong record labels are rejected before C entry",[]{
  auto s=signature(J::array({primitive("i64"),record("Box",J::array({field("value",0)}))}),J::array({1}),1);auto data=std::make_shared<Data>(Data::Record);data->text="Box";data->names={"wrong"};data->values={Value(42)};
  error("E_FFI_TYPE",[&]{typed(echo,s,{Value(data)});});
 });
 run("enum builders and discriminants follow the declared cases",[]{
  auto e=enumeration("Choice",J::array({variant("None",J::array()),variant("Some",J::array({field("value",0)}))}));
  auto s=signature(J::array({primitive("i64"),e}),J::array({0}),1);
  auto v=typed([](auto c,auto a,auto,auto o){nex_ffi_type type=0;uint64_t n=0;ok(api->result_type(c,&type));ok(api->type_variant_count(c,type,&n));require(n==2,"enum cases lost");return api->make_nominal(c,type,1,a,1,o);},s,{Value(42)});
  require(v.object->ordinal==1&&v.object->text=="Choice::Some"&&v.object->names[0]=="value","enum discriminant/layout differs");
 });
 run("C producer composes typed generic record enum and result owners",[]{
  auto types=J::array({primitive("bytes"),primitive("str"),record("interop::Packet<bytes>",J::array({field("data",0),field("text",1)})),enumeration("interop::Reply<bytes>",J::array({variant("Ready",J::array({field("packet",2)})),variant("Error",J::array({field("code",1)}))})),J{{"kind","result"},{"item",3}}});
  auto s=signature(types,J::array({0}),4);std::vector<uint8_t> bytes{0,255,128,1};std::vector<Value> args{Value(nexrt::bytes(ByteBuffer::copy(bytes)))};
  auto value=unwrap(invokeForeignTyped(nex_example_c_nominal,args,s));auto packet=value.object->values[0];require(value.object->text=="interop::Reply<bytes>::Ready"&&packet.object->text=="interop::Packet<bytes>"&&byteBuffer(packet.object->values[0].object).toVector()==bytes&&packet.object->values[1].object->text==std::string("Я\0",3)+"🧠","C typed composition differs");
 });
 run("borrowed function signatures cannot be relabelled",[]{
  auto types=J::array({J{{"kind","function"},{"name","fn()->i64"}},J{{"kind","function"},{"name","fn()->str"}}});auto wrong=signature(types,J::array({0}),1);auto fn=std::make_shared<Data>(Data::Closure);fn->text="target";
  error("E_FFI_TYPE",[&]{typed(echo,wrong,{Value(fn)});});auto correct=signature(J::array({types[0]}),J::array({0}),0);require(typed(echo,correct,{Value(fn)}).object==fn,"function owner lost");
 });
 run("nested callable authorities are discovered through aggregates",[]{
  auto s=signature(J::array({J{{"kind","function"},{"name","server fn()->i64"}},J{{"kind","list"},{"item",0}}}),J::array({1}),0);auto fn=std::make_shared<Data>(Data::Closure);auto list=std::make_shared<Data>(Data::List);list->values={Value(fn)};
  require(typed([](auto c,auto a,auto,auto o){return api->child(c,a[0],0,o);},s,{Value(list)}).object==fn,"nested function owner lost");
 });
 run("file owners preserve aliases while diagnostic identities are rejected",[]{
  auto s=signature(J::array({primitive("file")}),J::array({0}),0);Directory d;TextFiles files(d.root.string(),false);Value file(fileValue(files.open("input",FileMode::Read)));auto v=typed(echo,s,{file});require(equal(v,file),"typed file identity changed");fileResource(file.object).close();typed(echo,s,{file});
  error("E_FFI_TYPE",[&]{typed(echo,s,{Value(diagnosticFile(17))});});
 });
 run("recursive nominal schemas accept finite graphs and reject cycles",[]{
  auto s=signature(J::array({record("Node",J::array({field("children",1)})),J{{"kind","list"},{"item",0}}}),J::array({0}),0);
  auto node=std::make_shared<Data>(Data::Record),list=std::make_shared<Data>(Data::List);node->text="Node";node->names={"children"};node->values={Value(list)};typed(echo,s,{Value(node)});
  list->values={Value(node)};error("E_FFI_TYPE",[&]{typed(echo,s,{Value(node)});});list->values.clear();
 });
 run("value validation limits bound large graphs before C entry",[]{
  auto s=signature(J::array({primitive("i64"),J{{"kind","list"},{"item",0}}}),J::array({1}),1);auto list=std::make_shared<Data>(Data::List);list->values.resize(100000,Value(1));bool entered=false;unsigned polls=0;
  error("E_FFI_LIMIT",[&]{typed([&](auto,auto,auto,auto){entered=true;return NEX_FFI_OK;},s,{Value(list)},[&]{++polls;});});require(!entered&&polls>1000,"validation skipped node limits or cooperative polling");
 });
 run("expired cross-call and value tokens cannot name types",[]{
  auto s=integer();nex_ffi_call saved=0;nex_ffi_type type=0;
  typed([&](auto c,auto a,auto,auto o){saved=c;ok(api->result_type(c,&type));uint32_t k=99;require(api->type_kind(c,a[0],&k)==NEX_FFI_REF&&k==99,"value token became a type");*o=a[0];return NEX_FFI_OK;},s,{Value(42)});
  uint32_t kind=99;require(api->type_kind(saved,type,&kind)==NEX_FFI_SCOPE&&kind==99,"expired type context accepted");
  typed([&](auto c,auto a,auto,auto o){uint32_t k=99;require(api->type_kind(c,type,&k)==NEX_FFI_REF&&k==99,"cross-call type accepted");*o=a[0];return NEX_FFI_OK;},s,{Value(42)});
 });
 run("type metadata uses copied buffers and original signatures stay immutable",[]{
  auto s=integer();typed([](auto c,auto a,auto,auto o){uint64_t size=0,written=0;ok(api->signature_size(c,&size));std::string text(size,'\0');ok(api->copy_signature(c,0,reinterpret_cast<uint8_t*>(text.data()),size,&written));require(written==size&&J::parse(text).at("schema")=="nex.foreign-signature/1","signature copy differs");text.assign(size,'x');nex_ffi_type t=0;ok(api->result_type(c,&t));uint32_t k=0;ok(api->type_kind(c,t,&k));require(k==NEX_FFI_I64,"copied metadata mutated layout");*o=a[0];return NEX_FFI_OK;},s,{Value(42)});
 });
 run("typed state and schemas can be reused by independent threads",[]{
  auto s=integer();std::atomic<bool> failed=false;std::vector<std::thread> threads;for(unsigned i=0;i<8;++i)threads.emplace_back([&]{try{for(unsigned n=0;n<40;++n)if(typed(echo,s,{Value(42)}).scalar!=42)failed=true;}catch(...){failed=true;}});for(auto &t:threads)t.join();require(!failed,"shared immutable signature raced");
 });
 run("typed validation keeps original arguments before polling",[]{
  auto s=signature(J::array({primitive("str")}),J::array({0}),0);std::vector<Value> args{Value(string("held"))};Body body=echo;auto bridge=[](const nex_ffi_api_v1*,auto c,auto a,auto n,auto o,void *p)->nex_ffi_status{return (*static_cast<Body*>(p))(c,a,n,o);};auto v=invokeForeignTyped(bridge,args,s,&body,[&]{args.clear();});require(v.object->text=="held","typed input lost at entry poll");
 });
 run("host traps remain sticky during nominal construction",[]{
  auto s=signature(J::array({primitive("i64"),record("Box",J::array({field("value",0)}))}),J::array({0}),1);bool constructing=false,trapped=false;
  try{typed([&](auto c,auto a,auto,auto o){nex_ffi_type t=0;ok(api->result_type(c,&t));constructing=true;require(api->make_nominal(c,t,0,a,1,o)==NEX_FFI_HOST_TRAP,"constructor swallowed cancellation");return NEX_FFI_OK;},s,{Value(42)},[&]{if(constructing)throw Trap("E_CANCELLED","cancelled",71);});}catch(const Trap &e){trapped=e.code=="E_CANCELLED"&&e.line==71;}require(trapped,"typed host trap changed");
 });
 run("malformed signatures are rejected before callback invocation",[]{
  for(const auto &text:{std::string("{}"),std::string("{\"schema\":1,\"schema\":2}"),std::string(R"({"schema":"nex.foreign-signature/1","parameters":[0],"result":0,"types":[{"kind":"unit"}]})"),std::string(R"({"schema":"nex.foreign-signature/1","parameters":[],"result":0,"types":[{"kind":"list","item":0}]})"),std::string(R"({"schema":"nex.foreign-signature/1","parameters":[],"result":0,"types":[{"kind":"i64"},{"kind":"str"}]})")})error("E_FFI_SIGNATURE",[&]{ForeignSignature bad(text);});
  auto s=integer();auto moved=std::move(s);error("E_FFI_SIGNATURE",[&]{typed(echo,s,{Value(42)});});typed(echo,moved,{Value(42)});
 });
 std::cout<<count<<" cases passed\n";return 0;
}catch(const std::exception &e){std::cerr<<"FAIL "<<e.what()<<'\n';return 1;}}
